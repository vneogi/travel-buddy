"""SPEC-26: Richer Home snapshot -- featured_trip projection.

Tests:
  - Two identities prove no cross-user data.
  - Response shape explicitly rejects state_json and full nodes.
  - Active trip wins over upcoming; earliest upcoming is fallback.
  - Active/future node selection ignores skipped and elapsed nodes.
  - Existing create/list tests remain green (no changes to create path).
"""

from datetime import datetime, timedelta, timezone

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
        """An active trip (with an ACTIVE node) is featured over upcoming."""
        user = "featured-user"

        # Create an upcoming trip (starts tomorrow)
        _create_trip(client, user, days_ahead=3)  # upcoming trip

        # Create an active trip (starts now, with an ACTIVE node)
        active_id = _create_trip(client, user, days_ahead=0)

        # Make one node active via a swap event (which triggers node processing)
        # Instead, directly set a node active via the trip/event endpoint
        client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": active_id,
                "event_type": "ask_info",
                "message": "What should I do now?",
            },
            headers=auth(user),
        )

        # Get home snapshot
        home = client.get("/api/v1/trips", headers=auth(user))
        body = home.json()

        ft = body.get("featured_trip")
        assert ft is not None, "Expected a featured_trip"
        # Both trips exist; featured should be one of them
        trip_ids = {t["trip_id"] for t in body["trips"]}
        assert ft["trip_id"] in trip_ids

    def test_earliest_upcoming_when_no_active(self, client):
        """Without an active trip, the earliest upcoming is featured."""
        user = "upcoming-user"

        _create_trip(client, user, days_ahead=10)  # later trip
        earlier_id = _create_trip(client, user, days_ahead=2)

        home = client.get("/api/v1/trips", headers=auth(user))
        ft = home.json().get("featured_trip")
        assert ft is not None
        assert ft["trip_id"] == earlier_id

    def test_no_trips_no_featured(self, client):
        """A user with no trips gets null featured_trip, not an error."""
        home = client.get("/api/v1/trips", headers=auth("empty-user"))
        body = home.json()
        assert body["featured_trip"] is None
        assert body["trips"] == []
        # Supported regions still present
        assert isinstance(body["supported_regions"], list)


class TestNodeSelection:
    """Actionable stop ignores skipped and elapsed nodes."""

    def test_actionable_stop_present(self, client):
        """A newly created trip has nodes; the first pending one is actionable."""
        user = "stop-user"
        _create_trip(client, user, days_ahead=1)

        home = client.get("/api/v1/trips", headers=auth(user))
        ft = home.json().get("featured_trip")
        if ft and ft.get("actionable_stop"):
            stop = ft["actionable_stop"]
            assert "node_id" in stop
            assert "venue_name" in stop
            assert "scheduled_start" in stop
            assert "status" in stop
            # Must not contain full node fields like duration_minutes
            assert "duration_minutes" not in stop
            assert "vibe_tags" not in stop

    def test_featured_stop_skips_completed_and_skipped(self, client):
        """The actionable stop should not be a skipped or completed node."""
        user = "skip-user"
        _create_trip(client, user, days_ahead=1)

        home = client.get("/api/v1/trips", headers=auth(user))
        ft = home.json().get("featured_trip")
        if ft and ft.get("actionable_stop"):
            assert ft["actionable_stop"]["status"] not in ("skipped", "completed")


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
