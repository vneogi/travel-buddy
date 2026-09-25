"""Bounded SPEC-44 Phase A1-A3 integrity proofs."""

from datetime import datetime, timezone
import importlib
import os
from pathlib import Path
import uuid

import pytest

from models.schemas import (
    EventType,
    PartyMemberIn,
    TripNode,
    TripPartyIn,
    TripState,
)
from services.database_service import DatabaseService, db_service
from services.trip_persistence import CommandPayloadMismatch, TripVersionConflict


def _trip(user_id: str = "00000000-0000-0000-0000-000000000044") -> TripState:
    return TripState(
        user_id=user_id,
        nodes=[
            TripNode(
                node_id="spec44a1",
                venue_name="Atomic stop",
                scheduled_start=datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
            ),
            TripNode(
                node_id="spec44a2",
                venue_name="Second stop",
                scheduled_start=datetime(2026, 10, 1, 11, tzinfo=timezone.utc),
            ),
        ],
    )


def _commit(db: DatabaseService, trip: TripState, **overrides):
    kwargs = {
        "trip_state": trip,
        "command_id": "cmd-1",
        "command_type": "create_trip",
        "command_payload": {"kind": "create", "days": 1},
        "party": TripPartyIn(
            party_type="couple",
            size=2,
            members=[PartyMemberIn(role="self", age_band="adult")],
        ),
    }
    kwargs.update(overrides)
    return db.commit_trip_command(**kwargs)


def test_in_memory_atomic_rollback_injection_leaves_no_residue():
    db = DatabaseService()

    def fail_after_nodes(step: str) -> None:
        if step == "trip_node":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        _commit(db, _trip(), failure_injector=fail_after_nodes)

    assert db._trips == {}
    assert db._trip_nodes == {}
    assert db._trip_edges == {}
    assert db._parties == {}
    assert db._trip_commands == {}


def test_same_version_allows_one_success_then_one_conflict():
    db = DatabaseService()
    created = _commit(db, _trip()).trip_state
    first = created.model_copy(deep=True)
    second = created.model_copy(deep=True)
    first.nodes[0].venue_name = "First writer"
    second.nodes[0].venue_name = "Second writer"

    result = _commit(
        db,
        first,
        command_id="cmd-first",
        command_type="swap_activity",
        command_payload={"replacement": "first"},
        expected_version=1,
        party=None,
    )
    assert result.trip_state.version == 2

    with pytest.raises(TripVersionConflict):
        _commit(
            db,
            second,
            command_id="cmd-second",
            command_type="swap_activity",
            command_payload={"replacement": "second"},
            expected_version=1,
            party=None,
        )
    assert db.get_trip(created.trip_id).nodes[0].venue_name == "First writer"


def test_idempotent_replay_returns_first_result_without_second_effect():
    db = DatabaseService()
    first = _commit(db, _trip())
    replay = _commit(db, _trip())

    assert replay.replayed is True
    assert replay.trip_state.model_dump() == first.trip_state.model_dump()
    assert len(db._trip_commands) == 1
    assert db.get_trip(first.trip_state.trip_id).version == 1


def test_command_payload_mismatch_is_typed():
    db = DatabaseService()
    trip = _trip()
    _commit(db, trip)
    with pytest.raises(CommandPayloadMismatch):
        _commit(db, trip, command_payload={"kind": "different"})


def test_create_party_graph_and_command_share_one_uow():
    db = DatabaseService()
    result = _commit(db, _trip())
    trip_id = result.trip_state.trip_id

    assert result.trip_state.version == 1
    assert db.get_trip(trip_id) is not None
    assert len(db.get_trip_nodes(trip_id)) == 2
    assert len(db.get_trip_edges(trip_id)) == 1
    assert db.get_trip_party(trip_id).party_type == "couple"
    assert len(db._trip_commands) == 1


def test_observed_edge_duration_survives_mutation():
    db = DatabaseService()
    created = _commit(db, _trip()).trip_state
    edge = db.get_trip_edges(created.trip_id)[0]
    edge["observed_duration_minutes"] = 17
    changed = created.model_copy(deep=True)
    changed.nodes[0].venue_name = "Renamed only"

    _commit(
        db,
        changed,
        command_id="cmd-mutate",
        command_type="change_mood",
        command_payload={"mood": "calm"},
        expected_version=1,
        party=None,
    )
    assert db.get_trip_edges(created.trip_id)[0]["observed_duration_minutes"] == 17


def test_old_state_blob_defaults_to_version_one():
    db = DatabaseService()
    trip = _trip()
    old_blob = trip.model_dump(mode="json")
    old_blob.pop("version")
    db._trips[trip.trip_id] = old_blob
    assert db.get_trip(trip.trip_id).version == 1


def test_ask_info_does_not_bump_or_record_command(client, monkeypatch):
    user_id = "ask-spec44-user"
    db_service.get_or_create_user(user_id)
    trip = _trip(user_id)
    db_service.save_trip(trip)

    async def fake_process_event(**kwargs):
        return {
            "updated_trip_state": kwargs["trip_state"],
            "response": "Grounded answer",
            "routing_tier_used": "light",
            "from_cache": False,
            "schedule_warnings": [],
            "ask_response": None,
        }

    monkeypatch.setattr(
        "routers.trip_router.state_machine.process_event",
        fake_process_event,
    )
    response = client.post(
        "/api/v1/trip/event",
        headers={"X-Debug-User-Id": user_id},
        json={
            "trip_id": trip.trip_id,
            "event_type": EventType.ASK_INFO.value,
            "message": "What is next?",
            "command_id": "ask-command-must-not-persist",
            "expected_version": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert db_service.get_trip(trip.trip_id).version == 1
    assert db_service._trip_commands == {}


def test_http_version_conflict_uses_typed_409(client, monkeypatch):
    user_id = "conflict-spec44-user"
    db_service.get_or_create_user(user_id)
    trip = _trip(user_id)
    db_service.save_trip(trip)

    async def fake_process_event(**kwargs):
        return {
            "updated_trip_state": kwargs["trip_state"],
            "response": "Changed",
            "routing_tier_used": "light",
            "from_cache": False,
            "schedule_warnings": [],
        }

    monkeypatch.setattr(
        "routers.trip_router.state_machine.process_event",
        fake_process_event,
    )
    response = client.post(
        "/api/v1/trip/event",
        headers={"X-Debug-User-Id": user_id},
        json={
            "trip_id": trip.trip_id,
            "event_type": EventType.ADD_BOOKING.value,
            "message": "Add it",
            "command_id": "stale-command",
            "expected_version": 2,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "trip_version_conflict"


def test_http_payload_mismatch_uses_typed_409(client, monkeypatch):
    user_id = "mismatch-spec44-user"
    db_service.get_or_create_user(user_id)
    trip = _trip(user_id)
    db_service.save_trip(trip)
    db_service.commit_trip_command(
        trip_state=trip,
        command_id="reused-command",
        command_type=EventType.ADD_BOOKING.value,
        command_payload={"original": True},
        expected_version=1,
    )

    async def fake_process_event(**kwargs):
        return {
            "updated_trip_state": kwargs["trip_state"],
            "response": "Changed",
            "routing_tier_used": "light",
            "from_cache": False,
            "schedule_warnings": [],
        }

    monkeypatch.setattr(
        "routers.trip_router.state_machine.process_event",
        fake_process_event,
    )
    response = client.post(
        "/api/v1/trip/event",
        headers={"X-Debug-User-Id": user_id},
        json={
            "trip_id": trip.trip_id,
            "event_type": EventType.ADD_BOOKING.value,
            "message": "Different payload",
            "command_id": "reused-command",
            "expected_version": 2,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "command_payload_mismatch"


def test_migration_has_transaction_and_privilege_guards():
    sql = (
        Path(__file__).parents[1]
        / "supabase/migrations/0025_trip_command_integrity.sql"
    ).read_text()
    required = [
        "ADD COLUMN IF NOT EXISTS version",
        "CREATE TABLE IF NOT EXISTS trip_command",
        "SECURITY DEFINER",
        "SET search_path = public, pg_temp",
        "pg_advisory_xact_lock",
        "FOR UPDATE",
        "observed_duration_minutes",
        "REVOKE ALL ON FUNCTION",
        "FROM PUBLIC, anon, authenticated",
        "TO service_role",
    ]
    for guard in required:
        assert guard in sql
    assert "EXECUTE " not in sql.upper().replace("GRANT EXECUTE", "")


@pytest.mark.skipif(
    os.environ.get("TB_RUN_SPEC44_POSTGRES") != "1",
    reason="set TB_RUN_SPEC44_POSTGRES=1 after applying migration 0025",
)
def test_opt_in_postgres_rpc_replay_and_conflict(real_supabase_env):
    """Production-shaped RPC check; intentionally opt-in and non-transaction-proof."""
    pytest.importorskip("supabase")
    import services.supabase_service as service_module

    importlib.reload(service_module)
    db = service_module.get_supabase_service()
    assert db is not None

    user_id = str(uuid.uuid4())
    db.get_or_create_user(user_id)
    trip = _trip(user_id)
    created = _commit(db, trip)
    replay = _commit(db, trip)
    assert replay.replayed is True
    assert replay.trip_state.model_dump() == created.trip_state.model_dump()

    stale = created.trip_state.model_copy(deep=True)
    db.commit_trip_command(
        trip_state=stale,
        command_id="postgres-winner",
        command_type="change_mood",
        command_payload={"mood": "calm"},
        expected_version=1,
    )
    with pytest.raises(TripVersionConflict):
        db.commit_trip_command(
            trip_state=stale,
            command_id="postgres-loser",
            command_type="change_mood",
            command_payload={"mood": "busy"},
            expected_version=1,
        )
