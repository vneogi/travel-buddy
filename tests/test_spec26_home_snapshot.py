"""SPEC-26: Richer Home snapshot -- featured_trip projection.

Tests:
  - Two identities prove no cross-user data.
  - Response shape explicitly rejects state_json and full nodes.
  - Active trip wins over upcoming; earliest upcoming is fallback.
  - Active/future node selection ignores skipped and elapsed nodes.
  - Existing create/list tests remain green (no changes to create path).
"""

from datetime import datetime, timedelta, timezone

from models.schemas import NodeStatus, TripNode, TripState
from services.db_provider import db_service
from tests.conftest import auth


def _create_trip(client, user, region="dubai_uae", days_ahead=1):
    """Helper: create a trip and return the trip_id."""
    start = datetime.now(tz=timezone.utc) + timedelta(days=days_ahead)
    r = client.post(
        "/api/v1/trip/create",
        json={"geo_region": region, "start_date": start.isoformat()},
        headers=auth(user),
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


def _save_trip(user: str, trip_id: str, nodes: list[TripNode]) -> None:
    db_service.save_trip(
        TripState(
            trip_id=trip_id,
            user_id=user,
            geo_region="dubai_uae",
            nodes=nodes,
        )
    )


def _node(
    node_id: str,
    start: datetime,
    *,
    duration: int = 60,
    status: NodeStatus = NodeStatus.PENDING,
) -> TripNode:
    return TripNode(
        node_id=node_id,
        venue_id=f"venue-{node_id}",
        venue_name=f"Venue {node_id}",
        scheduled_start=start,
        duration_minutes=duration,
        status=status,
    )


class TestTwoIdentitiesNoLeak:
    """Two users each see only their own trips and featured_trip."""

    def test_separate_users(self, client):
        t1 = _create_trip(client, "alice")
        t2 = _create_trip(client, "bob")

        r1 = client.get("/api/v1/trips", headers=auth("alice"))
        r2 = client.get("/api/v1/trips", headers=auth("bob"))
        assert r1.status_code == 200
        assert r2.status_code == 200

        alice_ids = {t["trip_id"] for t in r1.json()["trips"]}
        bob_ids = {t["trip_id"] for t in r2.json()["trips"]}

        assert t1 in alice_ids
        assert t2 not in alice_ids
        assert t2 in bob_ids
        assert t1 not in bob_ids

        # featured_trip also scoped
        ft1 = r1.json().get("featured_trip")
        ft2 = r2.json().get("featured_trip")
        if ft1:
            assert ft1["trip_id"] == t1
        if ft2:
            assert ft2["trip_id"] == t2


class TestResponseShapeRejectsStateJson:
    """The /trips response must never include state_json or full nodes."""

    def test_no_state_json_in_trips(self, client):
        _create_trip(client, "shape-user")
        r = client.get("/api/v1/trips", headers=auth("shape-user"))
        body = r.json()

        # Top level: no state_json
        assert "state_json" not in body

        # Per-trip summaries: no state_json, no nodes list
        for trip in body["trips"]:
            assert "state_json" not in trip
            assert "nodes" not in trip

        # featured_trip: no state_json, no nodes list
        ft = body.get("featured_trip")
        if ft:
            assert "state_json" not in ft
            assert "nodes" not in ft


class TestFeaturedTripSelection:
    """Active trip wins; earliest upcoming is the fallback."""

    def test_active_wins_over_upcoming(self, client):
        """Time windows identify an active trip without an ACTIVE status."""
        user = "featured-user"
        now = datetime.now(tz=timezone.utc)
        _save_trip(
            user,
            "upcoming-trip",
            [_node("upcoming", now + timedelta(days=2))],
        )
        _save_trip(
            user,
            "active-trip",
            [_node("current", now - timedelta(minutes=15), duration=60)],
        )

        home = client.get("/api/v1/trips", headers=auth(user))
        featured = home.json()["featured_trip"]
        assert featured["trip_id"] == "active-trip"
        assert featured["is_active"] is True
        assert featured["actionable_stop"]["node_id"] == "current"
        assert featured["actionable_stop"]["status"] == "pending"

    def test_earliest_upcoming_when_no_active(self, client):
        """Without an active trip, the earliest upcoming is featured."""
        user = "upcoming-user"
        now = datetime.now(tz=timezone.utc)
        _save_trip(user, "later-trip", [_node("later", now + timedelta(days=10))])
        _save_trip(user, "earlier-trip", [_node("earlier", now + timedelta(days=2))])

        home = client.get("/api/v1/trips", headers=auth(user))
        featured = home.json()["featured_trip"]
        assert featured["trip_id"] == "earlier-trip"
        assert featured["is_active"] is False

    def test_no_trips_no_featured(self, client):
        """A user with no trips gets null featured_trip, not an error."""
        home = client.get("/api/v1/trips", headers=auth("empty-user"))
        body = home.json()
        assert body["featured_trip"] is None
        assert body["trips"] == []
        # Supported regions still present
        assert isinstance(body["supported_regions"], list)

    def test_naive_client_datetime_does_not_crash_home(self, client):
        """Flutter-selected local dates arrive without a timezone suffix."""
        naive_start = datetime.now() + timedelta(days=1)
        _save_trip("naive-user", "naive-trip", [_node("naive", naive_start)])

        home = client.get("/api/v1/trips", headers=auth("naive-user"))

        assert home.status_code == 200
        assert home.json()["featured_trip"]["trip_id"] == "naive-trip"

    def test_trip_without_actionable_nodes_is_not_featured(self, client):
        now = datetime.now(tz=timezone.utc)
        _save_trip(
            "done-user",
            "done-trip",
            [
                _node(
                    "done",
                    now + timedelta(hours=1),
                    status=NodeStatus.COMPLETED,
                )
            ],
        )

        home = client.get("/api/v1/trips", headers=auth("done-user"))

        assert home.status_code == 200
        assert home.json()["featured_trip"] is None


class TestNodeSelection:
    """Actionable stop ignores skipped and elapsed nodes."""

    def test_actionable_stop_present(self, client):
        """A newly created trip exposes a concrete actionable stop."""
        user = "stop-user"
        _create_trip(client, user, days_ahead=1)

        home = client.get("/api/v1/trips", headers=auth(user))
        stop = home.json()["featured_trip"]["actionable_stop"]
        assert stop is not None
        assert "node_id" in stop
        assert "venue_name" in stop
        assert "scheduled_start" in stop
        assert "status" in stop
        assert "duration_minutes" not in stop
        assert "vibe_tags" not in stop

    def test_featured_stop_skips_completed_and_skipped(self, client):
        """Skipped, completed and elapsed nodes cannot mask the next stop."""
        user = "skip-user"
        now = datetime.now(tz=timezone.utc)
        _save_trip(
            user,
            "mixed-trip",
            [
                _node(
                    "elapsed",
                    now - timedelta(hours=3),
                    status=NodeStatus.PENDING,
                ),
                _node(
                    "skipped",
                    now + timedelta(minutes=10),
                    status=NodeStatus.SKIPPED,
                ),
                _node(
                    "completed",
                    now + timedelta(minutes=20),
                    status=NodeStatus.COMPLETED,
                ),
                _node("next", now + timedelta(minutes=30)),
            ],
        )

        home = client.get("/api/v1/trips", headers=auth(user))
        stop = home.json()["featured_trip"]["actionable_stop"]
        assert stop["node_id"] == "next"


class TestExistingCreateListGreen:
    """Existing create/list behavior is preserved."""

    def test_create_trip_still_works(self, client):
        start = datetime.now(tz=timezone.utc) + timedelta(days=1)
        resp = client.post(
            "/api/v1/trip/create",
            json={"geo_region": "dubai_uae", "start_date": start.isoformat()},
            headers=auth("create-user"),
        )
        assert resp.status_code == 200
        assert "trip_id" in resp.json()

    def test_list_trips_still_returns_summaries(self, client):
        _create_trip(client, "list-user")
        r = client.get("/api/v1/trips", headers=auth("list-user"))
        assert r.status_code == 200
        trips = r.json()["trips"]
        assert len(trips) == 1
        assert "trip_id" in trips[0]
        assert "geo_region" in trips[0]
        assert "node_count" in trips[0]

    def test_supported_regions_present(self, client):
        r = client.get("/api/v1/trips", headers=auth("regions-user"))
        assert "supported_regions" in r.json()
        assert isinstance(r.json()["supported_regions"], list)
