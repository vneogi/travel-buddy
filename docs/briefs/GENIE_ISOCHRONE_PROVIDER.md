# Genie brief: network reachability provider + What Now filter

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

## 0. Context

Decision record: `docs/decisions/NETWORK_REACHABILITY.md`. The owner's
live trial (2026-11-16, `docs/briefs/ISOCHRONE_TRIAL_OWNER_RUN.md`)
showed material disagreement between Haversine walking and Google
Isochrones in Stone Town and Nungwi. Decision: earn the optional
enrichment slice.

This slice builds, server side only:

1. a reachability provider interface with a Google Isochrones
   implementation, a short-TTL cache, and a dedicated spend circuit
   (Gap 11 pattern);
2. one consumer: the SPEC-46 What Now "within N minutes" walking filter.

Default is OFF. With the flag off, What Now behaves exactly as today
except for one new envelope field. The owner turns it on later with a
Cloud Run env var. CI never calls Google.

Haversine stays the engine. The network polygon only removes candidates
that Haversine would keep; it never adds a candidate and never changes
`walk_min`, scheduling, or packing.

## 1. Goal

1. `services/geo_polygon.py`: production point-in-polygon for GeoJSON
   MultiPolygon in `[lng, lat]` order with holes (even-odd), identical
   results to `scripts/isochrone_trial.py` on the committed fixtures.
2. `services/reachability_provider.py`: `ReachabilityProvider` ABC,
   `GoogleIsochronesProvider`, closed-code `ReachabilityError`, TTL
   cache, dedicated spend circuit, and a factory that returns `None`
   when the flag is off or the key is missing.
3. What Now: when a provider is available and the context is a trip
   node with coordinates, fetch one walking isochrone from that node
   for the request's walking cap and drop candidates outside it. Any
   failure falls back to today's Haversine-only behaviour.
4. Envelope field `what_now.reachability_source`, closed set:
   `network_isochrone` | `haversine_estimate` | `not_applicable`.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm these exist on that SHA:
   `docs/decisions/NETWORK_REACHABILITY.md`,
   `scripts/isochrone_trial.py`, `data/isochrone_fixtures/`,
   `monitoring/spend_circuit.py`, `services/route_provider.py`,
   `tests/test_spec46_what_now.py`. If any is missing, stop.
3. Confirm `services/geo_polygon.py`,
   `services/reachability_provider.py`, and
   `origin/feat/isochrone-provider` do not exist.
4. Branch: `feat/isochrone-provider`.

## 3. Read before editing

- `docs/decisions/NETWORK_REACHABILITY.md` (whole file, including the
  owner live trial section)
- `docs/specs/SPEC-46-what-now-foreground-context.md` (Phase A
  determinism, closed reason codes, "Penciled: network reachability
  enrichment")
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `scripts/isochrone_trial.py`: `point_in_ring`, `point_in_polygon`,
  `point_in_multipolygon`, `polygons_from_geojson`, `fetch_isochrone`
  (request body and headers that worked live)
- `services/route_provider.py` (ABC + cache pattern to mirror)
- `monitoring/spend_circuit.py` (`SpendCircuit`, `SpendCapped`)
- `services/ask_service.py`: `_WALKING_CAPS`, `WhatNowRequest`,
  `_resolve_what_now_context`, `handle_what_now`
- `agents/state_machine.py`: the `preferences.mode == "what_now"`
  branch (around the `handle_what_now(` call)
- `config/settings.py` (`TB_` prefix; `google_maps_api_key`)
- `tests/test_spec46_what_now.py` (fixtures and harness to reuse)

## 4. Files you may touch

- `services/geo_polygon.py` (new)
- `services/reachability_provider.py` (new)
- `services/ask_service.py` (new async helper, one new optional
  parameter on `handle_what_now`, one envelope field; nothing else)
- `agents/state_machine.py` (the What Now branch only)
- `config/settings.py` (one field)
- `.env.example` (one line: `TB_REACHABILITY_PROVIDER=off`)
- `tests/test_reachability_provider.py` (new)
- `tests/test_what_now_network_reachability.py` (new)

Nothing else. Do not edit `scripts/isochrone_trial.py`, Flutter,
routers, `services/booking_constraints.py`, `services/scheduler.py`,
`services/catalog_itinerary.py`, `services/transit.py`, migrations,
`requirements*.txt`, or docs (the planning agent owns docs).

## 5. The change

### 5.1 Setting

`config/settings.py`, next to the Maps keys:

```
reachability_provider: str = "off"  # TB_REACHABILITY_PROVIDER: off | google_isochrones
```

Any value other than exactly `google_isochrones` means off.

### 5.2 `services/geo_polygon.py`

Pure functions, stdlib only, no I/O:

- `point_in_ring(lng, lat, ring) -> bool`
- `point_in_polygon(lng, lat, polygon) -> bool` (first ring exterior,
  later rings holes)
- `point_in_multipolygon(lng, lat, polygons) -> bool`
- `polygons_from_geojson(obj) -> list` accepting the Isochrones response
  (`isochrone.geoJson`), a bare `MultiPolygon`/`Polygon` geometry, a
  `Feature`, or a `FeatureCollection` -- same accepted shapes as the
  trial script.

Same semantics as the script. Coordinates are `[lng, lat]`. Do not
import the script from production code.

### 5.3 `services/reachability_provider.py`

```
class ReachabilityError(Exception):
    # code is one of: not_configured, invalid_input, spend_capped,
    # timeout, http_error, parse_error, origin_outside
    def __init__(self, code: str): ...

@dataclass(frozen=True)
class IsochroneResult:
    polygons: tuple          # parsed via geo_polygon.polygons_from_geojson
    minutes: int
    mode: str                # "walk"
    source: str              # "network_isochrone"
    observed_at: datetime    # UTC

class ReachabilityProvider(ABC):
    @abstractmethod
    async def walk_isochrone(
        self, lat: float, lng: float, minutes: int, identity: object
    ) -> IsochroneResult: ...
```

`GoogleIsochronesProvider(api_key, transport=None, spend_circuit=None,
clock=time.monotonic)`:

- Endpoint:
  `POST https://isochrones.googleapis.com/v1/isochrones:generate`.
- Headers: `Content-Type: application/json`,
  `X-Goog-Api-Key: <key>`, `X-Goog-FieldMask: *` (the mask proven in
  the owner's live run). The key goes in the header only, never in
  the URL.
- Body, exactly:
  `{"location": {"latitude": lat, "longitude": lng},
  "travelDuration": f"{minutes * 60}s", "travelMode": "WALK",
  "travelDirection": "FROM", "routingPreference": "TRAFFIC_UNAWARE",
  "enableSmoothing": false}`.
- `httpx.AsyncClient(transport=transport, timeout=3.0)`. `transport`
  is for tests (`httpx.MockTransport`). No new dependency.
- Validate input: finite lat/lng in range, `1 <= minutes <= 120`
  (WALK max is 7200 s); otherwise `ReachabilityError("invalid_input")`
  before any I/O.
- Cache: key `f"{round(lat,3)},{round(lng,3)}:{minutes}"`, TTL
  `CACHE_TTL_S = 3600`, at most `CACHE_MAX_ENTRIES = 256` (evict the
  oldest insert). A cache hit makes no HTTP call and records no spend.
- Spend: module-level
  `isochrone_spend_circuit = SpendCircuit(max_process_usd=1.50,
  max_identity_usd=0.15)` and `ISOCHRONE_EST_USD_PER_CALL = 0.003`
  (about 500 calls/day per process, 50 per identity). Before HTTP:
  `circuit.allow(identity, ISOCHRONE_EST_USD_PER_CALL)`; if false, raise
  `ReachabilityError("spend_capped")` without opening a socket. After a
  successful parse: `circuit.record(identity, ISOCHRONE_EST_USD_PER_CALL)`.
  Record even though Preview is free; this meters volume. Do not use
  `default_spend_circuit` (that one is the LLM budget).
- Errors map to closed codes: missing key -> `not_configured`;
  `httpx.TimeoutException` -> `timeout`; non-2xx or transport error ->
  `http_error`; bad JSON or no polygons -> `parse_error`; parsed
  polygons that do not contain the origin -> `origin_outside`.
  Do not cache failures.
- Logging: at most one `logger.info`/`warning` per call with the
  closed code only. Never log the key, the URL with params, lat/lng,
  or response bodies.

Factory:

```
def get_reachability_provider() -> Optional[ReachabilityProvider]:
```

Returns `None` unless `settings.reachability_provider ==
"google_isochrones"` and `settings.google_maps_api_key` is non-empty.
Otherwise returns one module-level singleton, so the cache survives
across requests. Tests reset it through a small `_reset_for_tests()`.

### 5.4 What Now wiring (`services/ask_service.py`)

New async helper:

```
async def fetch_what_now_reachability(
    request: WhatNowRequest,
    trip_nodes: List[Dict[str, Any]],
    now_utc,
    geo_region: str,
    provider: Optional[ReachabilityProvider],
    identity: object,
) -> Optional[tuple]:
```

- Returns `None` (no provider call) when: `provider is None`; the
  context resolves to `region_anchor` or `None`; the context node has
  no finite `lat`/`lng`.
- Origin is the context trip node's `lat`/`lng` from
  `_resolve_what_now_context`, the same node Haversine uses. Never
  read coordinates from preferences, headers, or any device field.
- Minutes = `_WALKING_CAPS[request.walking]` (15 / 25 / 45).
- Calls `await provider.walk_isochrone(...)`. On `ReachabilityError`,
  or on any other exception, returns `None`. What Now must never fail
  because of this provider.
- On success returns `result.polygons`.

`handle_what_now` gains one keyword-only parameter with default:
`reach_polygons: Optional[tuple] = None`. It stays sync and
deterministic given its inputs. Inside the candidate loop, after the
existing `walk_min > walking_cap` check and before the dwell checks:

```
if reach_polygons is not None and location_source == "trip_position":
    v_lat, v_lng = venue.get("lat"), venue.get("lng")
    if v_lat is not None and v_lng is not None:
        if not point_in_multipolygon(v_lng, v_lat, reach_polygons):
            continue
```

Leave everything else as it is: `walk_min` stays the Haversine
number; the sort, reason codes, `unknown_fields`, the next-booking
check, and the hotel boundary are unchanged. This gives an
intersection: a candidate must pass both the Haversine cap and the
network polygon.

Envelope, always present in `what_now_result`:

- `location_source == "region_anchor"` -> `"not_applicable"`
- `reach_polygons is not None` -> `"network_isochrone"`
- otherwise -> `"haversine_estimate"`

Do not add a reason code. Do not change the answer text.

### 5.5 State machine (`agents/state_machine.py`)

In the What Now branch only, before `handle_what_now(...)`:

```
from services.reachability_provider import get_reachability_provider
reach = await fetch_what_now_reachability(
    request=wn_req, trip_nodes=trip_nodes_dicts, now_utc=_now,
    geo_region=geo_region, provider=get_reachability_provider(),
    identity=user_id,
)
```

Pass `reach_polygons=reach` into `handle_what_now`. Touch no other
branch.

## 6. Tests

No test may open a real socket. Use `httpx.MockTransport` and stub
providers. Add a socket guard where a test exercises the provider.

`tests/test_reachability_provider.py`, exact names:

1. `test_geo_polygon_matches_trial_script_on_fixtures`: for every
   `data/isochrone_fixtures/*.geojson` and every catalog venue in that
   region, `services.geo_polygon.point_in_multipolygon` equals the
   script's result. Load the script by file path, as its own tests do.
2. `test_point_in_polygon_respects_hole`
3. `test_request_shape_and_key_in_header_only`: URL, method, both
   headers, exact body; the key does not appear in the URL.
4. `test_cache_hit_skips_second_http_call`
5. `test_cache_expires_after_ttl` (fake clock)
6. `test_cache_is_bounded`
7. `test_spend_cap_raises_before_any_http`: the transport is never
   called.
8. `test_success_records_spend_once_and_cache_hit_records_none`
9. `test_timeout_maps_to_closed_code`
10. `test_non_2xx_maps_to_http_error_and_is_not_cached`
11. `test_origin_outside_polygon_raises_origin_outside`
12. `test_invalid_minutes_rejected_without_io`
13. `test_logs_never_contain_key_or_coordinates` (caplog, across
    success and every error path)
14. `test_factory_off_by_default_returns_none`
15. `test_factory_without_key_returns_none`
16. `test_factory_returns_singleton_when_enabled`

`tests/test_what_now_network_reachability.py`, exact names (reuse the
`tests/test_spec46_what_now.py` fixtures):

1. `test_no_polygons_candidates_identical_to_baseline`: the same
   inputs with `reach_polygons=None` give the same `candidates` list
   as main; source is `haversine_estimate`.
2. `test_polygon_drops_haversine_near_venue_outside_network`
   (Forodhani-shaped case: within the Haversine cap, outside the
   polygon)
3. `test_polygon_never_adds_venue_beyond_haversine_cap`
4. `test_polygon_does_not_change_walk_minutes_or_sort_keys`
5. `test_provider_error_falls_back_to_haversine`: stub raises each
   `ReachabilityError` code and a bare `RuntimeError`; candidates equal
   the baseline and source is `haversine_estimate`.
6. `test_region_anchor_never_calls_provider_and_is_not_applicable`
7. `test_origin_is_context_node_coords_not_preferences`: the stub
   records `(lat, lng)`; preferences carrying `lat`/`lng`/`gps` keys are
   ignored.
8. `test_minutes_follow_walking_cap` (short/normal/longer -> 15/25/45)
9. `test_state_machine_what_now_passes_polygons_when_enabled`
   (monkeypatch `get_reachability_provider`)
10. `test_state_machine_what_now_flag_off_makes_no_provider_call`
11. `test_touched_files_are_ascii`

## 7. R17

Run each, confirm the named test fails, then restore:

A. Make `point_in_multipolygon` return `True` always:
   `test_polygon_drops_haversine_near_venue_outside_network` fails.
B. Skip the cache lookup:
   `test_cache_hit_skips_second_http_call` fails.
C. Skip the spend `allow` check:
   `test_spend_cap_raises_before_any_http` fails.
D. Use preference coordinates as the origin:
   `test_origin_is_context_node_coords_not_preferences` fails.

## 8. Stop rules

Stop and ask if:

- you need a new dependency;
- you are about to touch the next-booking check
  (`keeps_next_booking_reachable` / `_violates_next_booking`), the hotel
  boundary, Ask-to-Add, packing, swap, or Flutter;
- any test would reach Google;
- `handle_what_now` has callers that break with a keyword-only
  default parameter;
- the trial script and `geo_polygon` disagree on any fixture point.

## 9. Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

ruff 0.16.3. Zero failures expected. ASCII only.

## 10. Out of scope (later slices)

- Next-booking and hotel-return reachability via the network (decision
  step 2b)
- Showing the source in Flutter
- Drive / two-wheeler / ferry modes
- Map overlays
- Hosted enablement (owner env var after merge), deploy, APK

## 11. Delivery

One commit on `feat/isochrone-provider`:
`feat: optional Isochrones reachability for What Now walking filter`.
Push and verify the remote SHA. Do not merge. No `gh`.

## 12. Report

1. Base SHA.
2. Branch and remote SHA.
3. pytest last line.
4. ruff, format, and diff-check results.
5. Files touched, with +/- counts.
6. Results of R17 A, B, C, and D.
7. Confirmation that with the flag off, What Now candidates match main.
8. Confirmation that no test opened a socket.
9. Anything you were unsure about.
