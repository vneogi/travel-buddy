"""Travel Buddy MVP - State Machine

The core orchestration engine: maintains the active itinerary, processes
interruptions, and intelligently replaces activities.

Flow (non-cached):
  classify_intent -> check_cache -> venue_search -> apply_structural (with
  circuit breaker) -> generate_response

Lever 3 (Circuit Breaker): for structural edits, each candidate venue is
applied then re-scheduled+validated; if it makes a locked reservation
unreachable, the next candidate is tried, up to max_loop_depth attempts, after
which we fall back deterministically and leave the itinerary unchanged.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.settings import settings
from models.schemas import (
    TripState,
    TripNode,
    NodeStatus,
    RoutingTier,
    EventType,
    VenueSearchResult,
)
from services.db_provider import db_service
from services.cache_service import cache_service
from services.ask_service import AskService, AskPath, load_dish_glossary
import math
from datetime import timedelta as _td

from services.booking_constraints import (
    _ensure_aware,
    _local_date_of,
    find_constraining_flight,
    find_covering_hotel,
    hotel_morning_origin,
    is_first_unlocked_activity,
    is_last_unlocked_activity,
    violates_flight_cutoff,
    violates_hotel_return,
)
from services.catalog_itinerary import duration_for as _duration_for
from services.destination_tz import destination_tz as _dest_tz
from services.destination_tz import to_destination_local as _to_local
from services.destination_tz import parse_destination_wall_time as _parse_wall_time
from services.maps_service import maps_service
from services.opening_hours import HoursResult as _HoursResult
from services.transit import walking_minutes as _walking_minutes
from services.opening_hours import hours_for_slot as _hours_for_slot
from services.scheduler import reschedule_and_validate
from agents.router_agent import router_agent
from services.llm_service import llm_service


def _current_or_next_pending(nodes, now_utc):
    """Return the first pending node whose window has not fully elapsed.

    Skips completed, skipped, and fully-elapsed nodes so that a later-city
    corridor question uses the correct geo_region.
    """
    from datetime import timedelta

    for node in nodes:
        if node.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED):
            continue
        end = node.scheduled_start + timedelta(minutes=node.duration_minutes)
        if now_utc < end:
            return node
    return None


def _next_eligible_pending(nodes, current_node, now_utc):
    """Return the next pending node after *current_node*, skipping
    completed/skipped/elapsed.  Not simply index + 1."""
    from datetime import timedelta

    found_current = False
    for node in nodes:
        if node is current_node:
            found_current = True
            continue
        if not found_current:
            continue
        if node.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED):
            continue
        end = node.scheduled_start + timedelta(minutes=node.duration_minutes)
        if now_utc < end:
            return node
    return None


STRUCTURAL_EDIT_EVENTS = {
    EventType.CANCEL_ACTIVITY.value,
    EventType.SWAP_ACTIVITY.value,
    EventType.ADD_ACTIVITY.value,
    EventType.REROUTE.value,
    EventType.ADD_BOOKING.value,
    EventType.EDIT_BOOKING.value,
    EventType.DELETE_BOOKING.value,
}
VENUE_REQUIRED_EVENTS = {
    EventType.SWAP_ACTIVITY.value,
    EventType.ADD_ACTIVITY.value,
    EventType.REROUTE.value,
}


def _finite(v) -> bool:
    """True when v is a finite float/int (not None, NaN, or inf)."""
    return v is not None and math.isfinite(v)


def _same_local_day(a_start, b_start, geo_region) -> bool:
    """True when two UTC datetimes fall on the same destination-local calendar day."""
    tz = _dest_tz(geo_region)
    if tz is None:
        return a_start.date() == b_start.date()
    return a_start.astimezone(tz).date() == b_start.astimezone(tz).date()


def _is_swap_reachable(
    target_node: TripNode,
    cand_lat: Optional[float],
    cand_lng: Optional[float],
    cand_dwell: int,
    nodes: List[TripNode],
    target_idx: int,
) -> bool:
    """Unified swap reachability predicate (SPEC-41 A3b).

    Checks:
      1. prev-active -> candidate  (same region + same local day only)
      2. candidate -> next-locked  (same region + same local day only)

    Requires finite coordinates on the candidate and on every neighbour
    it is compared against.  Returns False when coords are missing.
    """
    if not _finite(cand_lat) or not _finite(cand_lng):
        return False

    target_region = getattr(target_node, "geo_region", None)

    # --- prev-active check (SPEC-10: hotel origin for first-of-day) ---
    prev_active = None
    for pi in range(target_idx - 1, -1, -1):
        pn = nodes[pi]
        if pn.status == NodeStatus.SKIPPED:
            continue
        if pn.node_kind == "booking" and pn.booking_type == "hotel":
            continue
        prev_active = pn
        break

    _used_hotel_origin = False
    if target_region:
        _slot_ld = _local_date_of(_ensure_aware(target_node.scheduled_start), target_region)
        _htl = find_covering_hotel(nodes, target_region, _slot_ld)
        if _htl is not None and is_first_unlocked_activity(
            target_node, nodes, target_region, _slot_ld
        ):
            if _finite(_htl.lat) and _finite(_htl.lng):
                _origin_instant = hotel_morning_origin(_htl, target_region, _slot_ld)
                if _origin_instant is not None:
                    _target_utc = _ensure_aware(target_node.scheduled_start)
                    if _target_utc >= _origin_instant:
                        _walk = _walking_minutes(_htl.lat, _htl.lng, cand_lat, cand_lng)
                        if _origin_instant + _td(minutes=_walk) > _target_utc:
                            return False
                        _used_hotel_origin = True

    if not _used_hotel_origin and prev_active is not None:
        pa_region = getattr(prev_active, "geo_region", None)
        if (
            pa_region
            and target_region
            and pa_region == target_region
            and _same_local_day(
                prev_active.scheduled_start,
                target_node.scheduled_start,
                target_region,
            )
        ):
            if not _finite(prev_active.lat) or not _finite(prev_active.lng):
                return False
            prev_end = prev_active.scheduled_start + _td(minutes=prev_active.duration_minutes)
            transfer = _walking_minutes(prev_active.lat, prev_active.lng, cand_lat, cand_lng)
            if prev_end + _td(minutes=transfer) > target_node.scheduled_start:
                return False

    # --- next-locked check ---
    next_lock = None
    for ni in range(target_idx + 1, len(nodes)):
        nn = nodes[ni]
        if nn.status == NodeStatus.SKIPPED:
            continue
        if nn.node_kind == "booking" and nn.booking_type == "hotel":
            continue
        nn_region = getattr(nn, "geo_region", None)
        if nn_region != target_region:
            break
        if not _same_local_day(target_node.scheduled_start, nn.scheduled_start, target_region):
            break
        if nn.is_locked:
            next_lock = nn
            break

    if next_lock is not None:
        if not _finite(next_lock.lat) or not _finite(next_lock.lng):
            return False
        cand_end = target_node.scheduled_start + _td(minutes=cand_dwell)
        transfer = _walking_minutes(cand_lat, cand_lng, next_lock.lat, next_lock.lng)
        if cand_end + _td(minutes=transfer) > next_lock.scheduled_start:
            return False

    # --- SPEC-10: flight cutoff (scoped to future flights, same region) ---
    if target_region:
        fl = find_constraining_flight(nodes, target_node)
        if fl is not None:
            if violates_flight_cutoff(
                target_node.scheduled_start,
                cand_dwell,
                fl,
                activity_lat=cand_lat,
                activity_lng=cand_lng,
            ):
                return False

    # --- SPEC-10: hotel return wall (only last unlocked of the day) ---
    if target_region and _finite(cand_lat) and _finite(cand_lng):
        _slot_ld2 = _local_date_of(_ensure_aware(target_node.scheduled_start), target_region)
        if is_last_unlocked_activity(target_node, nodes, target_region, _slot_ld2):
            hotel = find_covering_hotel(nodes, target_region, _slot_ld2)
            if hotel is not None:
                if violates_hotel_return(
                    target_node.scheduled_start,
                    cand_dwell,
                    hotel,
                    target_region,
                    _slot_ld2,
                    activity_lat=cand_lat,
                    activity_lng=cand_lng,
                ):
                    return False

    return True


class TripStateMachine:
    """State machine for trip management."""

    def __init__(self):
        self.max_loop_depth = settings.max_loop_depth

    async def process_event(
        self,
        trip_state: TripState,
        event_type: str,
        message: str,
        target_node_id: Optional[str] = None,
        preferences: Optional[dict] = None,
        now_utc: Optional[datetime] = None,
        user_id: str = "anonymous",
        is_anonymous: bool = True,
    ) -> Dict:
        state = {
            "trip_state": trip_state,
            "event_type": event_type,
            "now_utc": now_utc,
            "message": message,
            "target_node_id": target_node_id,
            "preferences": preferences or {},
            "loop_depth": 0,
            "routing_tier": RoutingTier.LIGHT,
            "from_cache": False,
            "venues_found": [],
            "response": "",
            "schedule_warnings": [],
            "breaker_tripped": False,
            "no_candidates": False,
            "user_id": user_id,
            "is_anonymous": is_anonymous,
        }

        # Bug #4: ASK_INFO bypasses legacy semantic cache entirely
        is_ask = event_type == EventType.ASK_INFO.value

        state = self._node_classify_intent(state)
        if not is_ask:
            state = self._node_check_cache(state)

        if not state["from_cache"]:
            state = self._node_venue_search(state)
            state = self._node_apply_structural(state)
            state = await self._node_generate_response(state)
            # Only cache non-ASK LIGHT responses -- never mutations.
            if (
                not is_ask
                and state["routing_tier"] == RoutingTier.LIGHT
                and state["event_type"] not in STRUCTURAL_EDIT_EVENTS
            ):
                trip = state["trip_state"]
                now_utc = state.get("now_utc") or datetime.now(timezone.utc)
                cn = _current_or_next_pending(trip.nodes, now_utc)
                geo = getattr(cn, "geo_region", None) or trip.geo_region or ""
                venue = cn.venue_name if cn else ""
                cache_service.store_response(
                    state["message"],
                    state["response"],
                    geo_region=geo,
                    venue_name=venue,
                )

        # Bug #1: copy ask_response onto return dict
        result = {
            "updated_trip_state": state["trip_state"],
            "response": state["response"],
            "routing_tier_used": state["routing_tier"].value,
            "from_cache": state["from_cache"],
            "venues_found": state["venues_found"],
            "schedule_warnings": state.get("schedule_warnings") or [],
        }
        if "ask_response" in state:
            result["ask_response"] = state["ask_response"]
        return result

    # =========================================================================
    # Graph Nodes
    # =========================================================================

    def _node_classify_intent(self, state: Dict) -> Dict:
        tier, confidence = router_agent.classify_intent(state["message"], state["event_type"])
        state["routing_tier"] = tier
        state["confidence"] = confidence
        return state

    def _node_check_cache(self, state: Dict) -> Dict:
        """Light requests only \u2014 structural edits always need fresh processing."""
        if (
            state["routing_tier"] == RoutingTier.LIGHT
            and state["event_type"] not in STRUCTURAL_EDIT_EVENTS
        ):
            # Resolve context for cache key so the same question
            # in different regions never shares a cache entry.
            trip = state["trip_state"]
            now_utc = state.get("now_utc") or datetime.now(timezone.utc)
            cn = _current_or_next_pending(trip.nodes, now_utc)
            geo = getattr(cn, "geo_region", None) or trip.geo_region or ""
            venue = cn.venue_name if cn else ""
            cache_result = cache_service.check_cache(
                state["message"],
                geo_region=geo,
                venue_name=venue,
            )
            if cache_result:
                response_text, _ = cache_result
                state["response"] = response_text
                state["from_cache"] = True
        return state

    def _node_venue_search(self, state: Dict) -> Dict:
        if state["routing_tier"] != RoutingTier.HEAVY:
            return state

        # SPEC-29: Cancel never needs venue search
        if state["event_type"] not in VENUE_REQUIRED_EVENTS:
            return state

        trip_state: TripState = state["trip_state"]
        user_lat = trip_state.current_context.location_lat
        user_lng = trip_state.current_context.location_lng
        target_node = next(
            (node for node in trip_state.nodes if node.node_id == state.get("target_node_id")),
            None,
        )

        # A sheet selection is an explicit choice, not another search prompt.
        # Resolve the stable ID server-side so the event applies exactly the
        # venue the traveller tapped without trusting client-supplied venue data.
        replacement_id = state["preferences"].get("replacement_venue_id")
        if state["event_type"] == EventType.SWAP_ACTIVITY.value and replacement_id:
            if target_node and target_node.venue_id == replacement_id:
                state["no_candidates"] = True
                return state
            replacement = db_service.get_venue_by_id(replacement_id)
            target_region = (
                target_node.geo_region if target_node else None
            ) or trip_state.geo_region
            if replacement is None or (
                replacement.geo_region and target_region and replacement.geo_region != target_region
            ):
                state["no_candidates"] = True
                return state
            # SPEC-41 A2: refuse CLOSED for the target slot
            structured = getattr(replacement, "opening_hours_structured", None)
            if target_node is not None:
                cand_dwell = _duration_for(
                    {"typical_dwell_minutes": getattr(replacement, "typical_dwell_minutes", None)}
                )
                hr = _hours_for_slot(
                    structured,
                    target_node.scheduled_start,
                    cand_dwell,
                    target_region,
                )
                if hr == _HoursResult.CLOSED:
                    state["no_candidates"] = True
                    return state
                # SPEC-41 A3b: unified reachability predicate
                target_idx = trip_state.nodes.index(target_node)
                if not _is_swap_reachable(
                    target_node,
                    getattr(replacement, "lat", None),
                    getattr(replacement, "lng", None),
                    cand_dwell,
                    trip_state.nodes,
                    target_idx,
                ):
                    state["no_candidates"] = True
                    return state
            state["venues_found"] = [
                VenueSearchResult(
                    venue=replacement,
                    similarity_score=0.0,
                    final_score=0.0,
                )
            ]
            return state

        search_query = state["message"]
        if state["preferences"].get("mood"):
            search_query += f" {state['preferences']['mood']}"
        if state["preferences"].get("vibe"):
            search_query += f" {state['preferences']['vibe']}"

        # Use the target node's city for structural changes. The last itinerary
        # node is not a safe proxy once a trip spans multiple cities.
        geo_region = (target_node.geo_region if target_node else None) or trip_state.geo_region

        venues = db_service.hybrid_venue_search(
            query=search_query,
            user_lat=user_lat,
            user_lng=user_lng,
            vibe_filter=state["preferences"].get("vibe_tags"),
            audience_filter=state["preferences"].get("audience"),
            geo_region=geo_region,
        )
        if state["event_type"] == EventType.SWAP_ACTIVITY.value and target_node:
            venues = [result for result in venues if result.venue.venue_id != target_node.venue_id]

        # SPEC-41 A2: hydrate + hours-filter swap search candidates.
        # Hybrid-search RPC may omit opening_hours_structured / typical_dwell_minutes;
        # hydrate each candidate from the catalog so the predicate sees real data.
        if (
            state["event_type"] == EventType.SWAP_ACTIVITY.value
            and target_node is not None
            and venues
        ):
            eligible = []
            for v in venues:
                hydrated = db_service.get_venue_by_id(v.venue.venue_id)
                if hydrated is None:
                    continue  # unhydratable candidate discarded
                v = VenueSearchResult(
                    venue=hydrated,
                    similarity_score=v.similarity_score,
                    final_score=v.final_score,
                )
                structured = getattr(v.venue, "opening_hours_structured", None)
                cand_dwell = _duration_for(
                    {"typical_dwell_minutes": getattr(v.venue, "typical_dwell_minutes", None)}
                )
                hr = _hours_for_slot(
                    structured,
                    target_node.scheduled_start,
                    cand_dwell,
                    geo_region,
                )
                if hr == _HoursResult.CLOSED:
                    continue

                # SPEC-41 A3b: unified reachability predicate
                target_idx = trip_state.nodes.index(target_node)
                if not _is_swap_reachable(
                    target_node,
                    getattr(v.venue, "lat", None),
                    getattr(v.venue, "lng", None),
                    cand_dwell,
                    trip_state.nodes,
                    target_idx,
                ):
                    continue

                eligible.append(v)
            venues = eligible

        # Maps validation -- swap uses target-slot structured hours as the sole
        # hours authority; do not call validate_venues (which uses datetime.now()).
        if venues and state["event_type"] != EventType.SWAP_ACTIVITY.value:
            venue_dicts = [
                {
                    "name": v.venue.name,
                    "lat": v.venue.lat,
                    "lng": v.venue.lng,
                    "opening_hours": v.venue.opening_hours,
                }
                for v in venues
            ]
            validated = maps_service.validate_venues(venue_dicts, user_lat, user_lng)
            validated_names = {v["name"] for v in validated}
            venues = [v for v in venues if v.venue.name in validated_names]

        # Keep several candidates so the circuit breaker has alternatives to try.
        state["venues_found"] = venues[:5]
        return state

    def _node_apply_structural(self, state: Dict) -> Dict:
        """Apply a structural edit with reschedule + circuit breaker.

        Non-structural HEAVY events (change_mood / weather_alert) and LIGHT
        events don\'t mutate the itinerary here.
        """
        event_type = state["event_type"]
        if event_type not in STRUCTURAL_EDIT_EVENTS:
            return state

        trip_state: TripState = state["trip_state"]
        venues: List[VenueSearchResult] = state["venues_found"]
        target = state.get("target_node_id")

        # SPEC-10: Booking anchors bypass venue search entirely
        if event_type == EventType.ADD_BOOKING.value:
            prefs = state.get("preferences") or {}
            raw_start = prefs.get("scheduled_start") or state.get("message")
            booking_region = prefs.get("geo_region") or trip_state.geo_region
            try:
                start_dt = _parse_wall_time(raw_start, booking_region)
            except (ValueError, TypeError):
                start_dt = datetime.now(tz=timezone.utc)

            booking_node = TripNode(
                venue_name=prefs.get("venue_name") or prefs.get("title") or "Booking",
                scheduled_start=start_dt,
                duration_minutes=int(prefs.get("duration_minutes", 90)),
                is_locked=True,
                status=NodeStatus.PENDING,
                micro_location=prefs.get("micro_location"),
                lat=prefs.get("lat"),
                lng=prefs.get("lng"),
                geo_region=prefs.get("geo_region") or trip_state.geo_region,
                node_kind="booking",
                booking_type=prefs.get("booking_type", "flight"),
                confirmation_code=prefs.get("confirmation_code"),
                booking_notes=prefs.get("booking_notes"),
                import_source=prefs.get("import_source", "manual"),
            )
            nodes = list(trip_state.nodes)
            inserted = False
            for i, n in enumerate(nodes):
                if n.scheduled_start > booking_node.scheduled_start:
                    nodes.insert(i, booking_node)
                    inserted = True
                    break
            if not inserted:
                nodes.append(booking_node)
            result = reschedule_and_validate(nodes, mutated_node_ids={booking_node.node_id})
            trip_state.nodes = result.nodes
            state["schedule_warnings"] = result.warnings
            return state

        # SPEC-10: Edit an existing booking (patch supplied fields only)
        if event_type == EventType.EDIT_BOOKING.value:
            target_id = state.get("target_node_id")
            prefs = state.get("preferences") or {}
            node = next(
                (n for n in trip_state.nodes if n.node_id == target_id),
                None,
            )
            if node is None:
                return state
            # Patch only supplied fields; preserve node_id, lock, omitted
            if "venue_name" in prefs:
                node.venue_name = prefs["venue_name"]
            if "booking_type" in prefs:
                node.booking_type = prefs["booking_type"]
            if "confirmation_code" in prefs:
                node.confirmation_code = prefs["confirmation_code"]
            if "booking_notes" in prefs:
                node.booking_notes = prefs["booking_notes"]
            if "import_source" in prefs:
                node.import_source = prefs["import_source"]
            schedule_changed = False
            if "duration_minutes" in prefs:
                new_duration = int(prefs["duration_minutes"])
                if new_duration != node.duration_minutes:
                    node.duration_minutes = new_duration
                    schedule_changed = True
            if "micro_location" in prefs:
                node.micro_location = prefs["micro_location"]
            if "lat" in prefs:
                node.lat = prefs["lat"]
            if "lng" in prefs:
                node.lng = prefs["lng"]
            if "geo_region" in prefs:
                node.geo_region = prefs["geo_region"]
            if "scheduled_start" in prefs:
                raw = prefs["scheduled_start"]
                edit_region = (
                    prefs.get("geo_region")
                    or getattr(node, "geo_region", None)
                    or trip_state.geo_region
                )
                try:
                    new_start = _parse_wall_time(raw, edit_region)
                    if new_start != node.scheduled_start:
                        node.scheduled_start = new_start
                        schedule_changed = True
                except (ValueError, TypeError):
                    pass
            # node_kind and is_locked are NEVER changed by edit
            assert node.node_kind == "booking"
            assert node.is_locked is True
            if schedule_changed:
                # Re-sort into chronological order and reschedule
                nodes = list(trip_state.nodes)
                nodes.remove(node)
                inserted = False
                for i, n in enumerate(nodes):
                    if n.scheduled_start > node.scheduled_start:
                        nodes.insert(i, node)
                        inserted = True
                        break
                if not inserted:
                    nodes.append(node)
                result = reschedule_and_validate(nodes, mutated_node_ids={target_id})
                trip_state.nodes = result.nodes
                state["schedule_warnings"] = result.warnings
            return state

        # SPEC-10: Delete an existing booking (remove, not skip)
        if event_type == EventType.DELETE_BOOKING.value:
            target_id = state.get("target_node_id")
            trip_state.nodes = [n for n in trip_state.nodes if n.node_id != target_id]
            result = reschedule_and_validate(list(trip_state.nodes), mutated_node_ids=set())
            trip_state.nodes = result.nodes
            state["schedule_warnings"] = result.warnings
            return state

        # SPEC-29 D4: Cancel uses a direct status-flip; no venue loop needed.
        if event_type == EventType.CANCEL_ACTIVITY.value:
            target = state.get("target_node_id")
            for node in trip_state.nodes:
                if node.node_id == target:
                    if node.is_locked:
                        # Refuse: locked nodes cannot be canceled.
                        return state
                    node.status = NodeStatus.SKIPPED
                    break
            result = reschedule_and_validate(list(trip_state.nodes), mutated_node_ids={target})
            trip_state.nodes = result.nodes
            state["schedule_warnings"] = result.warnings
            return state

        if event_type in VENUE_REQUIRED_EVENTS and not venues:
            state["no_candidates"] = True
            state["schedule_warnings"] = ["No suitable venues found for this change."]
            return state

        accepted = None
        attempt = 0
        while attempt < self.max_loop_depth:
            candidate_nodes = self._build_candidate_nodes(
                trip_state, event_type, target, venues, attempt
            )
            if candidate_nodes is None:
                break  # no further candidates to try
            if not candidate_nodes:
                # Apply-time recheck failed; advance to next candidate
                attempt += 1
                continue
            # SPEC-41 A2: scope warnings to actually-mutated nodes
            original_map = {n.node_id: n for n in trip_state.nodes}
            _mutated = set()
            for cn in candidate_nodes:
                orig = original_map.get(cn.node_id)
                if orig is None:
                    _mutated.add(cn.node_id)
                elif (
                    cn.venue_id != orig.venue_id
                    or cn.duration_minutes != orig.duration_minutes
                    or cn.scheduled_start != orig.scheduled_start
                ):
                    _mutated.add(cn.node_id)
            result = reschedule_and_validate(candidate_nodes, mutated_node_ids=_mutated)
            state["loop_depth"] = attempt + 1
            if not result.has_hard_conflict:
                accepted = result
                break
            attempt += 1

        if accepted is not None:
            trip_state.nodes = accepted.nodes
            state["schedule_warnings"] = accepted.warnings
        else:
            # Circuit breaker: no feasible candidate within max_loop_depth.
            state["breaker_tripped"] = True
            state["schedule_warnings"] = [
                "Couldn't find a change that keeps your locked reservations reachable in time."
            ]

        trip_state.updated_at = datetime.now(tz=timezone.utc)
        state["trip_state"] = trip_state
        return state

    def _build_candidate_nodes(
        self,
        trip_state: TripState,
        event_type: str,
        target_node_id: Optional[str],
        venues: List[VenueSearchResult],
        attempt: int,
    ) -> Optional[List[TripNode]]:
        """Return a fresh node list with the edit applied for this attempt, or
        None when there is no further candidate to try."""
        nodes = [n.model_copy(deep=True) for n in trip_state.nodes]

        if event_type == EventType.CANCEL_ACTIVITY.value:
            if attempt > 0:
                return None
            for node in nodes:
                if node.node_id == target_node_id and not node.is_locked:
                    node.status = NodeStatus.SKIPPED
                    break
            return nodes

        if event_type == EventType.SWAP_ACTIVITY.value:
            if attempt >= len(venues):
                return None
            venue = venues[attempt].venue
            cand_dwell = _duration_for(
                {"typical_dwell_minutes": getattr(venue, "typical_dwell_minutes", None)}
            )
            # Find the target slot in the fresh copy
            target_idx = None
            for i, node in enumerate(nodes):
                if node.node_id == target_node_id and not node.is_locked:
                    target_idx = i
                    break
            if target_idx is None:
                return None

            # Apply-time reachability recheck (SPEC-41 A3b)
            target_node = nodes[target_idx]
            geo_region = getattr(target_node, "geo_region", None) or trip_state.geo_region
            structured = getattr(venue, "opening_hours_structured", None)
            hr = _hours_for_slot(structured, target_node.scheduled_start, cand_dwell, geo_region)
            if hr == _HoursResult.CLOSED:
                return []  # advance to next candidate

            cand_lat = getattr(venue, "lat", None)
            cand_lng = getattr(venue, "lng", None)
            if not _is_swap_reachable(
                target_node, cand_lat, cand_lng, cand_dwell, nodes, target_idx
            ):
                return []  # advance to next candidate

            nodes[target_idx] = self._node_from_venue(
                venue, target_node.scheduled_start, cand_dwell, target_node.node_id
            )
            return nodes

        if event_type == EventType.ADD_ACTIVITY.value:
            if attempt >= len(venues):
                return None
            venue = venues[attempt].venue
            insert_at = len(nodes)
            if target_node_id:
                for i, node in enumerate(nodes):
                    if node.node_id == target_node_id:
                        insert_at = i + 1
                        break
            anchor = (
                nodes[insert_at - 1].scheduled_start
                if insert_at > 0 and nodes
                else datetime.now(tz=timezone.utc)
            )
            nodes.insert(
                insert_at,
                self._node_from_venue(venue, anchor, 90, None),
            )
            return nodes

        if event_type == EventType.REROUTE.value:
            window = venues[attempt:]
            if not window:
                return None
            vi = 0
            for i, node in enumerate(nodes):
                if not node.is_locked and node.status == NodeStatus.PENDING and vi < len(window):
                    nodes[i] = self._node_from_venue(
                        window[vi].venue,
                        node.scheduled_start,
                        node.duration_minutes,
                        node.node_id,
                    )
                    vi += 1
            return nodes

        return None

    @staticmethod
    def _node_from_venue(venue, scheduled_start, duration_minutes, node_id) -> TripNode:
        kwargs = dict(
            venue_name=venue.name,
            venue_id=venue.venue_id,
            scheduled_start=scheduled_start or datetime.now(tz=timezone.utc),
            duration_minutes=duration_minutes,
            is_locked=False,
            status=NodeStatus.PENDING,
            micro_location=venue.micro_location,
            vibe_tags=venue.vibe_tags,
            lat=venue.lat,
            lng=venue.lng,
            opening_hours=getattr(venue, "opening_hours", None),
            opening_hours_structured=getattr(venue, "opening_hours_structured", None),
            geo_region=getattr(venue, "geo_region", None),
            names_local=getattr(venue, "names_local", None),
            landmarks_local=getattr(venue, "landmarks_local", None),
            nearest_landmark=getattr(venue, "nearest_landmark", None),
        )
        if node_id is not None:
            kwargs["node_id"] = node_id
        return TripNode(**kwargs)

    async def _node_generate_response(self, state: Dict) -> Dict:
        """Node: produce the user-facing text (LLM when configured, else canned)."""
        # SPEC-29 D4: Cancel is fully deterministic -- no LLM, no RAG.
        if state["event_type"] == EventType.CANCEL_ACTIVITY.value:
            target = state.get("target_node_id")
            trip_state: TripState = state["trip_state"]
            target_node = next((n for n in trip_state.nodes if n.node_id == target), None)
            if target_node and target_node.is_locked:
                # Locked nodes cannot be canceled -- refuse calmly.
                state["response"] = (
                    f"'{target_node.venue_name}' is a locked booking and "
                    "cannot be canceled. Unlock it first if you need to remove it."
                )
                # Do not mutate state -- node stays unchanged.
                return state
            if target_node:
                state["response"] = f"Canceled {target_node.venue_name}."
            else:
                state["response"] = "Activity canceled."
            return state

        if state["event_type"] == EventType.ADD_BOOKING.value:
            state["response"] = "Booking saved as a locked itinerary anchor."
            return state

        if state["event_type"] == EventType.EDIT_BOOKING.value:
            state["response"] = "Booking updated."
            return state

        if state["event_type"] == EventType.DELETE_BOOKING.value:
            state["response"] = "Booking removed from your itinerary."
            return state

        # SPEC-25: Grounded trip-scoped Ask -- retrieval-first
        if state["event_type"] == EventType.ASK_INFO.value:
            return await self._handle_grounded_ask(state)

        if state.get("breaker_tripped"):
            state["response"] = self._fallback_response(state)
            return state

        if state.get("no_candidates"):
            state["response"] = (
                "I couldn't find a suitable alternative nearby that fits your "
                "preferences and transit range, so your itinerary is unchanged."
            )
            return state

        # SPEC-41: swap_activity uses a deterministic response -- never LLM.
        # Placed AFTER no_candidates / breaker_tripped so a refused swap
        # keeps the honest refusal and never says "Swapped to ...".
        if state["event_type"] == EventType.SWAP_ACTIVITY.value:
            target_id = state.get("target_node_id")
            trip = state["trip_state"]
            applied = next((n for n in trip.nodes if n.node_id == target_id), None)
            if applied is not None:
                state["response"] = f"Swapped to {applied.venue_name}."
            else:
                state["response"] = "Activity swapped."
            return state

        if settings.litellm_api_key or settings.gemini_api_key:
            # Build destination context BEFORE try so the except clause
            # can use it regardless of whether the HEAVY or LIGHT path
            # threw.  Also used for cache keying and router fallback.
            trip = state["trip_state"]
            now_utc = state.get("now_utc") or datetime.now(timezone.utc)
            target_id = state.get("target_node_id")
            current_node = None
            next_node = None
            if target_id:
                current_node = next(
                    (n for n in trip.nodes if n.node_id == target_id),
                    None,
                )
            if current_node is None:
                current_node = _current_or_next_pending(trip.nodes, now_utc)
            if current_node:
                next_node = _next_eligible_pending(trip.nodes, current_node, now_utc)
            info_ctx = {
                "geo_region": (getattr(current_node, "geo_region", None) or trip.geo_region or ""),
            }
            if current_node:
                info_ctx["venue_name"] = current_node.venue_name
            if next_node:
                info_ctx["next_venue_name"] = next_node.venue_name

            try:
                if state["routing_tier"] == RoutingTier.HEAVY:
                    venues = [
                        {
                            "name": v.venue.name,
                            "micro_location": v.venue.micro_location,
                            "vibe_tags": v.venue.vibe_tags,
                            "lat": v.venue.lat,
                            "lng": v.venue.lng,
                        }
                        for v in state["venues_found"]
                    ]
                    base = await llm_service.generate_itinerary_response(
                        user_message=state["message"],
                        trip_state=state["trip_state"].model_dump(mode="json"),
                        venues_found=venues,
                        routing_tier="heavy",
                        context=info_ctx,
                    )
                else:
                    base = await llm_service.generate_info_response(
                        state["message"],
                        context=info_ctx,
                    )
                state["response"] = base
            except Exception as exc:
                print(f"LLM generation failed, using canned fallback: {exc}")
                state["response"] = router_agent.generate_response(
                    state["message"],
                    state["routing_tier"],
                    {
                        "venues_found": state["venues_found"],
                        "geo_region": info_ctx.get("geo_region", ""),
                    },
                )
        else:
            trip = state["trip_state"]
            now_utc = state.get("now_utc") or datetime.now(timezone.utc)
            cn = _current_or_next_pending(trip.nodes, now_utc)
            fallback_geo = (
                (getattr(cn, "geo_region", None) or trip.geo_region or "")
                if cn
                else (trip.geo_region or "")
            )
            info_ctx = {"geo_region": fallback_geo}
            if cn:
                info_ctx["venue_name"] = cn.venue_name
            state["response"] = router_agent.generate_response(
                state["message"],
                state["routing_tier"],
                {
                    "venues_found": state["venues_found"],
                    "target_node_id": state.get("target_node_id", ""),
                    "geo_region": fallback_geo,
                },
            )

        return state

    async def _handle_grounded_ask(self, state: Dict) -> Dict:
        """SPEC-25: Grounded trip-scoped Ask via retrieval-first pipeline.

        Ask never persists itinerary nodes. Mutations return a proposal
        for the confirmation sheet.
        """
        trip = state["trip_state"]
        now_utc = state.get("now_utc") or datetime.now(timezone.utc)
        target_id = state.get("target_node_id")

        current_node = None
        next_node = None
        if target_id:
            current_node = next((n for n in trip.nodes if n.node_id == target_id), None)
        if current_node is None:
            current_node = _current_or_next_pending(trip.nodes, now_utc)
        if current_node:
            next_node = _next_eligible_pending(trip.nodes, current_node, now_utc)

        geo_region = getattr(current_node, "geo_region", None) or trip.geo_region or ""
        venue_name = current_node.venue_name if current_node else None
        venue_id = getattr(current_node, "venue_id", None) if current_node else None
        next_venue_name = next_node.venue_name if next_node else None

        current_summary = None
        if current_node:
            local_start = _to_local(current_node.scheduled_start, geo_region)
            current_summary = (
                f"{current_node.venue_name} at "
                f"{local_start.strftime('%H:%M')} "
                f"({current_node.duration_minutes} min)"
            )
        next_summary = None
        if next_node:
            # Use the next node's own geo_region for timezone conversion,
            # not the current node's, so cross-city corridors are correct.
            next_geo = getattr(next_node, "geo_region", None) or geo_region
            local_start = _to_local(next_node.scheduled_start, next_geo)
            next_summary = (
                f"{next_node.venue_name} at "
                f"{local_start.strftime('%H:%M')} "
                f"({next_node.duration_minutes} min)"
            )

        # Bug #9: per-request glossary, exact region match
        dish_glossary = load_dish_glossary(geo_region)
        ask_svc = AskService(
            llm_service=llm_service,
            db=db_service,
            dish_glossary=dish_glossary,
        )

        user_id = state.get("user_id", "anonymous")
        is_anonymous = state.get("is_anonymous", True)
        llm_key_present = bool(settings.litellm_api_key or settings.gemini_api_key)

        ask_resp = await ask_svc.handle_ask(
            question=state["message"],
            geo_region=geo_region,
            user_id=user_id,
            is_anonymous=is_anonymous,
            venue_name=venue_name,
            venue_id=venue_id or "",
            next_venue_name=next_venue_name,
            current_node_summary=current_summary,
            next_node_summary=next_summary,
            llm_key_present=llm_key_present,
            target_node_id=state.get("target_node_id"),
        )

        state["response"] = ask_resp.answer
        # Bug #1: structured Ask envelope for downstream.
        # Proposal must match PlanChangeProposal schema when present.
        proposal_dict = None
        if ask_resp.proposal is not None:
            proposal_dict = {
                "event_type": ask_resp.proposal.get("event_type", "swap_activity"),
                "target_node_id": ask_resp.proposal.get("target_node_id", ""),
                "summary": ask_resp.proposal.get("summary", ""),
            }
        state["ask_response"] = {
            "answer": ask_resp.answer,
            "tier": ask_resp.tier.value,
            "path": ask_resp.path.value,
            "intent": ask_resp.intent.value,
            "source_ids": ask_resp.source_ids,
            "source_class": ask_resp.source_class,
            "from_cache": ask_resp.from_cache,
            "fallback_reason": ask_resp.fallback_reason,
            "proposal": proposal_dict,
            "food_disclaimer": ask_resp.food_disclaimer,
        }
        return state

    def _fallback_response(self, state: Dict) -> str:
        return (
            "I couldn't safely rework the schedule around your locked "
            "reservations for this request, so nothing was changed. Try a "
            "different activity, a nearer venue, or freeing up a locked slot. "
            "Your locked reservations remain intact."
        )


# Singleton instance
state_machine = TripStateMachine()
