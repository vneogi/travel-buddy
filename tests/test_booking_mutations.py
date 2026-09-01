"""SPEC-10 Booking Edit and Delete -- backend tests.

Sabotage proofs:
  S1: Recreate booking with new node_id -> test_edit_preserves_node_id_and_lock fails
  S2: Put edit/delete in quota set -> test_edit_does_not_consume_quota fails
  S3: Route through heavy model -> test_edit_does_not_invoke_llm fails
  S4: Delete by cancel/skip -> test_delete_removes_rather_than_skips fails
  S5: Drop omitted field during edit -> test_partial_edit_preserves_omitted_fields fails
  S6: Bypass delete confirmation -> client test (Keep-zero-call) fails
  S7: Remove notes from card sig -> client test (notes-only render) fails
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import auth
from services.database_service import db_service


@pytest.fixture()
def trip_with_booking(client):
    """Create a trip then add a booking; return (trip_id, booking_node)."""
    created = client.post(
        "/api/v1/trip/create",
        headers=auth("mut-user"),
        json={"start_date": "2026-10-05T09:00:00"},
    ).json()
    trip_id = created["trip_id"]

    added = client.post(
        "/api/v1/trip/event",
        headers=auth("mut-user"),
        json={
            "trip_id": trip_id,
            "event_type": "add_booking",
            "message": "Add flight",
            "preferences": {
                "venue_name": "EK501 to Dubai",
                "booking_type": "flight",
                "scheduled_start": "2026-10-05T14:00:00Z",
                "duration_minutes": 180,
                "confirmation_code": "SEC-1234",
                "booking_notes": "Window seat requested",
                "import_source": "manual",
            },
        },
    )
    assert added.status_code == 200
    nodes = added.json()["updated_nodes"]
    booking = next(n for n in nodes if n["node_kind"] == "booking")
    return trip_id, booking


class TestEditBooking:
    """S1: Recreate with new ID -> fails. S5: Drop omitted -> fails."""

    def test_edit_preserves_node_id_and_lock(self, client, trip_with_booking):
        trip_id, booking = trip_with_booking
        original_id = booking["node_id"]

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Edit booking",
                "target_node_id": original_id,
                "preferences": {"venue_name": "EK502 to Dubai"},
            },
        )
        assert r.status_code == 200
        nodes = r.json()["updated_nodes"]
        edited = next(n for n in nodes if n["node_kind"] == "booking")
        assert edited["node_id"] == original_id  # S1: stable ID
        assert edited["is_locked"] is True
        assert edited["node_kind"] == "booking"
        assert edited["venue_name"] == "EK502 to Dubai"

    def test_partial_edit_preserves_omitted_fields(self, client, trip_with_booking):
        """S5: Only notes change; code, type, source survive."""
        trip_id, booking = trip_with_booking

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Update notes",
                "target_node_id": booking["node_id"],
                "preferences": {"booking_notes": "Aisle now"},
            },
        )
        assert r.status_code == 200
        nodes = r.json()["updated_nodes"]
        edited = next(n for n in nodes if n["node_id"] == booking["node_id"])
        assert edited["booking_notes"] == "Aisle now"
        assert edited["confirmation_code"] == "SEC-1234"
        assert edited["booking_type"] == "flight"
        assert edited["import_source"] == "manual"
        assert edited["venue_name"] == "EK501 to Dubai"

    def test_unchanged_time_and_duration_do_not_reschedule(
        self, client, trip_with_booking
    ):
        """The client submits unchanged schedule fields on a notes-only edit."""
        trip_id, booking = trip_with_booking

        with patch("agents.state_machine.reschedule_and_validate") as reschedule:
            r = client.post(
                "/api/v1/trip/event",
                headers=auth("mut-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "edit_booking",
                    "message": "Update notes",
                    "target_node_id": booking["node_id"],
                    "preferences": {
                        "booking_notes": "Aisle now",
                        "scheduled_start": booking["scheduled_start"],
                        "duration_minutes": booking["duration_minutes"],
                    },
                },
            )

        assert r.status_code == 200
        reschedule.assert_not_called()

    def test_time_edit_reorders_same_node(self, client, trip_with_booking):
        """Move booking to earlier time; same node_id ends up re-sorted."""
        trip_id, booking = trip_with_booking
        original_id = booking["node_id"]

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Move earlier",
                "target_node_id": original_id,
                "preferences": {"scheduled_start": "2026-10-05T07:00:00Z"},
            },
        )
        assert r.status_code == 200
        nodes = r.json()["updated_nodes"]
        edited = next(n for n in nodes if n["node_id"] == original_id)
        assert edited["scheduled_start"].startswith("2026-10-05T07:00")
        # Same node, reordered
        assert edited["node_id"] == original_id

    def test_hotel_edit_remains_background_anchor(self, client):
        """Edited hotel keeps booking_type=hotel and background anchor behavior."""
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("hotel-user"),
            json={"start_date": "2026-10-05T09:00:00"},
        ).json()
        trip_id = created["trip_id"]

        added = client.post(
            "/api/v1/trip/event",
            headers=auth("hotel-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "Ritz Carlton",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-05T15:00:00Z",
                    "duration_minutes": 720,
                },
            },
        )
        nodes = added.json()["updated_nodes"]
        hotel = next(n for n in nodes if n.get("booking_type") == "hotel")

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("hotel-user"),
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Update hotel",
                "target_node_id": hotel["node_id"],
                "preferences": {"booking_notes": "Late check-in"},
            },
        )
        assert r.status_code == 200
        nodes = r.json()["updated_nodes"]
        edited = next(n for n in nodes if n["node_id"] == hotel["node_id"])
        assert edited["booking_type"] == "hotel"
        assert edited["is_locked"] is True


class TestDeleteBooking:
    """S4: Delete by cancel/skip -> fails."""

    def test_delete_removes_rather_than_skips(self, client, trip_with_booking):
        trip_id, booking = trip_with_booking
        node_id = booking["node_id"]

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "delete_booking",
                "message": "Delete flight",
                "target_node_id": node_id,
            },
        )
        assert r.status_code == 200
        nodes = r.json()["updated_nodes"]
        assert all(n["node_id"] != node_id for n in nodes)
        assert all(
            not (n.get("node_kind") == "booking" and n.get("status") == "skipped")
            for n in nodes
        )

    def test_delete_reschedules_remaining(self, client, trip_with_booking):
        trip_id, booking = trip_with_booking

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "delete_booking",
                "message": "Remove it",
                "target_node_id": booking["node_id"],
            },
        )
        assert r.status_code == 200
        assert len(r.json()["updated_nodes"]) >= 1


class TestTargetValidation:
    def test_missing_target_returns_404(self, client):
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("val-user"),
            json={"start_date": "2026-10-05T09:00:00"},
        ).json()

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("val-user"),
            json={
                "trip_id": created["trip_id"],
                "event_type": "edit_booking",
                "message": "Edit",
                "target_node_id": "nonexistent-id",
            },
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "target_not_found"

    def test_non_booking_target_returns_409(self, client):
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("val-user"),
            json={"start_date": "2026-10-05T09:00:00"},
        ).json()
        trip_id = created["trip_id"]
        activity_id = created["nodes"][0]["node_id"]

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("val-user"),
            json={
                "trip_id": trip_id,
                "event_type": "delete_booking",
                "message": "Delete",
                "target_node_id": activity_id,
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "target_not_a_booking"

    def test_missing_target_node_id_returns_400(self, client):
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("val-user"),
            json={"start_date": "2026-10-05T09:00:00"},
        ).json()

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("val-user"),
            json={
                "trip_id": created["trip_id"],
                "event_type": "edit_booking",
                "message": "Edit",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "missing_target_node_id"


class TestQuotaAndRouting:
    """S2: edit/delete in quota set -> fails. S3: heavy route -> fails."""

    def test_edit_does_not_consume_quota(self, client, trip_with_booking):
        trip_id, booking = trip_with_booking
        before = db_service.get_or_create_user("mut-user").daily_reroute_count

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Edit",
                "target_node_id": booking["node_id"],
                "preferences": {"booking_notes": "Changed"},
            },
        )
        assert r.status_code == 200
        after = db_service.get_or_create_user("mut-user").daily_reroute_count
        assert after == before

    def test_delete_does_not_consume_quota(self, client, trip_with_booking):
        trip_id, booking = trip_with_booking
        before = db_service.get_or_create_user("mut-user").daily_reroute_count

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "delete_booking",
                "message": "Delete",
                "target_node_id": booking["node_id"],
            },
        )
        assert r.status_code == 200
        assert r.json()["routing_tier_used"] == "light"
        after = db_service.get_or_create_user("mut-user").daily_reroute_count
        assert after == before

    def test_edit_does_not_invoke_llm(self, client, trip_with_booking):
        """S3: The response is canned; no LLM call."""
        trip_id, booking = trip_with_booking

        with patch(
            "agents.state_machine.llm_service.generate_info_response",
            new_callable=AsyncMock,
        ) as generate:
            r = client.post(
                "/api/v1/trip/event",
                headers=auth("mut-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "edit_booking",
                    "message": "Edit",
                    "target_node_id": booking["node_id"],
                    "preferences": {"booking_notes": "Test"},
                },
            )
        generate.assert_not_awaited()
        assert r.status_code == 200
        assert r.json()["routing_tier_used"] == "light"
        assert "Booking updated" in r.json()["message"]

    def test_delete_does_not_invoke_llm(self, client, trip_with_booking):
        trip_id, booking = trip_with_booking

        with patch(
            "agents.state_machine.llm_service.generate_info_response",
            new_callable=AsyncMock,
        ) as generate:
            r = client.post(
                "/api/v1/trip/event",
                headers=auth("mut-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "delete_booking",
                    "message": "Delete",
                    "target_node_id": booking["node_id"],
                },
            )
        generate.assert_not_awaited()
        assert r.status_code == 200
        assert r.json()["routing_tier_used"] == "light"
        assert "removed" in r.json()["message"].lower()


class TestPrivacy:
    def test_confirmation_code_absent_from_logs(self, client, trip_with_booking, caplog):
        """No log line may contain the confirmation code."""
        trip_id, booking = trip_with_booking

        with caplog.at_level(logging.DEBUG):
            client.post(
                "/api/v1/trip/event",
                headers=auth("mut-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "edit_booking",
                    "message": "Edit code",
                    "target_node_id": booking["node_id"],
                    "preferences": {"confirmation_code": "TOP-SECRET-99"},
                },
            )

        full_log = caplog.text
        assert "TOP-SECRET-99" not in full_log
        assert "SEC-1234" not in full_log


class TestLockedCancelUnchanged:
    def test_locked_cancel_still_refuses(self, client, trip_with_booking):
        """SPEC-30 locked cancel behavior remains unchanged."""
        trip_id, booking = trip_with_booking

        r = client.post(
            "/api/v1/trip/event",
            headers=auth("mut-user"),
            json={
                "trip_id": trip_id,
                "event_type": "cancel_activity",
                "message": "Cancel booking",
                "target_node_id": booking["node_id"],
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "locked_cancel_refused"
