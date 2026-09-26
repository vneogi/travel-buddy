"""SPEC-44 Phase A: PostgreSQL transaction proofs.

These tests run against a real ephemeral PostgreSQL instance with
migrations 0001-0025 applied.  They prove transaction atomicity,
isolation, idempotency, and privilege constraints that in-memory
adapter tests and static SQL-string checks cannot cover.

Skip condition: ``TB_SPEC44_PG_DSN`` environment variable must point
to an initialized database.  Default ``pytest tests/`` on a runner
without Postgres skips every test with an explicit reason.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from textwrap import dedent

import pytest

PG_DSN = os.environ.get("TB_SPEC44_PG_DSN")

pytestmark = pytest.mark.skipif(
    not PG_DSN,
    reason="TB_SPEC44_PG_DSN not set; ephemeral PostgreSQL proofs skipped",
)


def _pg_connect(dsn: str | None = None):
    """Return a fresh psycopg2 connection (autocommit OFF).

    Each caller is responsible for commit/rollback.  The JWT claim
    is set per-call inside _call_commit so it lives in the same
    transaction as the RPC.
    """
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn or PG_DSN)
    conn.autocommit = False
    # Register the jsonb adapter so SELECT commit_trip_command(...)
    # returns a Python dict, not a JSON string.
    psycopg2.extras.register_default_jsonb(conn)
    return conn


def _service_role_cursor(conn):
    """Return a cursor with service_role session variable set."""
    cur = conn.cursor()
    cur.execute("SELECT set_config('request.jwt.claim.role', 'service_role', true)")
    return cur


def _payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _ensure_user(conn, user_id: str) -> None:
    """Insert a test user into user_tiers if not already present."""
    cur = conn.cursor()
    cur.execute(
        dedent("""\
            INSERT INTO user_tiers (user_id, identity_kind, max_daily_reroutes)
            VALUES (%s, 'unknown', 10)
            ON CONFLICT (user_id) DO NOTHING
        """),
        (user_id,),
    )
    conn.commit()
    cur.close()


def _state_json(trip_id: str, user_id: str) -> dict:
    return {
        "trip_id": trip_id,
        "user_id": user_id,
        "version": 1,
        "geo_region": "luang_prabang_laos",
        "nodes": [
            {
                "node_id": f"n-{trip_id[:8]}-1",
                "venue_name": "Atomic stop",
                "scheduled_start": "2026-10-01T09:00:00+00:00",
                "duration_minutes": 90,
                "is_locked": False,
                "status": "planned",
                "vibe_tags": [],
            },
            {
                "node_id": f"n-{trip_id[:8]}-2",
                "venue_name": "Second stop",
                "scheduled_start": "2026-10-01T11:00:00+00:00",
                "duration_minutes": 90,
                "is_locked": False,
                "status": "planned",
                "vibe_tags": [],
            },
        ],
    }


def _nodes_json(trip_id: str) -> list[dict]:
    """Match the shape decompose_trip always sends."""
    return [
        {
            "node_id": f"n-{trip_id[:8]}-1",
            "day_index": 0,
            "seq": 1,
            "node_type": "activity",
            "title": "Atomic stop",
            "scheduled_start": "2026-10-01T09:00:00+00:00",
            "scheduled_end": "2026-10-01T10:30:00+00:00",
            "duration_minutes": 90,
            "is_locked": False,
            "status": "planned",
            "geo_region": "luang_prabang_laos",
            "node_kind": "activity",
            "vibe_tags": [],
        },
        {
            "node_id": f"n-{trip_id[:8]}-2",
            "day_index": 0,
            "seq": 2,
            "node_type": "activity",
            "title": "Second stop",
            "scheduled_start": "2026-10-01T11:00:00+00:00",
            "scheduled_end": "2026-10-01T12:30:00+00:00",
            "duration_minutes": 90,
            "is_locked": False,
            "status": "planned",
            "geo_region": "luang_prabang_laos",
            "node_kind": "activity",
            "vibe_tags": ["culture"],
        },
    ]


def _edges_json(trip_id: str) -> list[dict]:
    return [
        {
            "edge_id": f"e-{trip_id[:8]}-1",
            "from_node_id": f"n-{trip_id[:8]}-1",
            "to_node_id": f"n-{trip_id[:8]}-2",
            "transport_mode": "walking",
            "expected_duration_minutes": 15,
        },
    ]


def _call_commit(
    conn,
    trip_id: str,
    user_id: str,
    command_id: str,
    command_type: str = "create_trip",
    payload: dict | None = None,
    expected_version: int | None = None,
    consume_reroute: bool = False,
    response_data: dict | None = None,
) -> dict:
    """Call commit_trip_command RPC and return the JSONB result."""
    if payload is None:
        payload = {"kind": "create"}
    cur = _service_role_cursor(conn)
    cur.execute(
        dedent("""\
            SELECT commit_trip_command(
                p_trip_id := %s::UUID,
                p_user_id := %s::UUID,
                p_command_id := %s,
                p_command_type := %s,
                p_payload_hash := %s,
                p_expected_version := %s,
                p_state_json := %s::JSONB,
                p_nodes := %s::JSONB,
                p_edges := %s::JSONB,
                p_party := NULL,
                p_response_data := %s::JSONB,
                p_consume_reroute := %s
            )
        """),
        (
            trip_id,
            user_id,
            command_id,
            command_type,
            _payload_hash(payload),
            expected_version,
            json.dumps(_state_json(trip_id, user_id)),
            json.dumps(_nodes_json(trip_id)),
            json.dumps(_edges_json(trip_id)),
            json.dumps(response_data) if response_data else None,
            consume_reroute,
        ),
    )
    result = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return result


def _count_rows(conn, table: str, trip_id: str) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table} WHERE trip_id = %s::UUID", (trip_id,))  # noqa: S608
    n = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return n


# =====================================================================
# Proof 1: Atomic create commits trip, nodes, edges, and command
# =====================================================================
class TestAtomicCreate:
    def test_create_commits_all_tables(self):
        """A successful create must persist trip_states, trip_node,
        trip_edge, and trip_command in one transaction."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        result = _call_commit(conn, trip_id, user_id, "create-pg-1")
        assert result["status"] == "committed"
        assert _count_rows(conn, "trip_states", trip_id) == 1
        assert _count_rows(conn, "trip_node", trip_id) == 2
        assert _count_rows(conn, "trip_edge", trip_id) == 1
        assert _count_rows(conn, "trip_command", trip_id) == 1
        conn.close()

    def test_rpc_failure_leaves_no_residue(self):
        """If the RPC raises (e.g. invalid input), no partial state
        must remain.  We trigger this with an oversized command_id."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        import psycopg2

        with pytest.raises(psycopg2.errors.DataException):
            _call_commit(conn, trip_id, user_id, command_id="x" * 200)  # exceeds 128-char CHECK
        # Connection is in error state after exception; reset it.
        conn.rollback()
        assert _count_rows(conn, "trip_states", trip_id) == 0
        assert _count_rows(conn, "trip_node", trip_id) == 0
        assert _count_rows(conn, "trip_edge", trip_id) == 0
        assert _count_rows(conn, "trip_command", trip_id) == 0
        conn.close()


# =====================================================================
# Proof 2: Optimistic concurrency -- version conflict
# =====================================================================
class TestVersionConflict:
    def test_two_writers_same_version_one_succeeds_one_conflicts(self):
        """Two concurrent writes against the same expected_version
        must produce exactly one success and one typed conflict."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        # Create the trip first.
        result = _call_commit(conn, trip_id, user_id, "create-v1")
        assert result["status"] == "committed"

        def write(cmd_id: str):
            c = _pg_connect()
            _ensure_user(c, user_id)
            r = _call_commit(
                c,
                trip_id,
                user_id,
                cmd_id,
                command_type="change_mood",
                payload={"mood": cmd_id},
                expected_version=1,
            )
            c.close()
            return r

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(write, "writer-a"),
                pool.submit(write, "writer-b"),
            ]
        results = [f.result() for f in futures]
        statuses = sorted(r["status"] for r in results)
        assert statuses == ["committed", "trip_version_conflict"]

        # Trip must be at version 2 (one successful bump).
        cur = conn.cursor()
        cur.execute("SELECT version FROM trip_states WHERE trip_id = %s::UUID", (trip_id,))
        assert cur.fetchone()[0] == 2
        cur.close()
        conn.close()


# =====================================================================
# Proof 3: Idempotent command replay
# =====================================================================
class TestIdempotentReplay:
    def test_replay_returns_first_outcome_without_second_effect(self):
        """The same command_id + payload must return the first recorded
        outcome with status='replayed' and not create a second trip."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        first = _call_commit(conn, trip_id, user_id, "idem-1")
        assert first["status"] == "committed"

        replay = _call_commit(conn, trip_id, user_id, "idem-1")
        assert replay["status"] == "replayed"
        assert replay["trip_state"] == first["trip_state"]
        assert _count_rows(conn, "trip_command", trip_id) == 1
        conn.close()

    def test_payload_mismatch_returns_typed_conflict(self):
        """Reusing a command_id with a different payload must return
        command_payload_mismatch, not a silent replay."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        first = _call_commit(conn, trip_id, user_id, "mismatch-1", payload={"kind": "original"})
        assert first["status"] == "committed"

        conflict = _call_commit(conn, trip_id, user_id, "mismatch-1", payload={"kind": "different"})
        assert conflict["status"] == "command_payload_mismatch"
        conn.close()

    def test_concurrent_same_command_produces_one_effect(self):
        """Two threads submitting the same command_id concurrently must
        produce one committed and one replayed, not two effects."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        # Create the trip first (version 1).
        _call_commit(conn, trip_id, user_id, "setup-concurrent")

        def retry(label: str):
            c = _pg_connect()
            _ensure_user(c, user_id)
            r = _call_commit(
                c,
                trip_id,
                user_id,
                "same-cmd",
                command_type="change_mood",
                payload={"mood": "calm"},
                expected_version=1,
            )
            c.close()
            return r

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(retry, ["A", "B"]))
        statuses = sorted(r["status"] for r in results)
        assert statuses == ["committed", "replayed"]
        assert results[0]["trip_state"] == results[1]["trip_state"]
        conn.close()


# =====================================================================
# Proof 4: Reroute quota atomicity
# =====================================================================
class TestRerouteQuota:
    def test_quota_consumed_atomically_with_mutation(self):
        """consume_reroute inside the RPC must increment the counter
        exactly once for a successful mutation."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        _call_commit(conn, trip_id, user_id, "quota-setup")

        result = _call_commit(
            conn,
            trip_id,
            user_id,
            "quota-use",
            command_type="change_mood",
            payload={"mood": "rain"},
            expected_version=1,
            consume_reroute=True,
        )
        assert result["status"] == "committed"

        cur = conn.cursor()
        cur.execute(
            "SELECT daily_reroute_count FROM user_tiers WHERE user_id = %s::UUID", (user_id,)
        )
        assert cur.fetchone()[0] == 1
        cur.close()
        conn.close()

    def test_version_conflict_does_not_consume_quota(self):
        """A losing concurrent write must not consume a reroute."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        _call_commit(conn, trip_id, user_id, "quota-conflict-setup")
        # First mutation succeeds (version 1 -> 2).
        _call_commit(
            conn,
            trip_id,
            user_id,
            "quota-conflict-win",
            command_type="change_mood",
            payload={"m": "a"},
            expected_version=1,
            consume_reroute=True,
        )
        # Second mutation with stale version must conflict.
        loser = _call_commit(
            conn,
            trip_id,
            user_id,
            "quota-conflict-lose",
            command_type="change_mood",
            payload={"m": "b"},
            expected_version=1,
            consume_reroute=True,
        )
        assert loser["status"] == "trip_version_conflict"

        cur = conn.cursor()
        cur.execute(
            "SELECT daily_reroute_count FROM user_tiers WHERE user_id = %s::UUID", (user_id,)
        )
        assert cur.fetchone()[0] == 1, "losing write must not consume quota"
        cur.close()
        conn.close()


# =====================================================================
# Proof 5: Graph mutation replaces atomically
# =====================================================================
class TestGraphMutation:
    def test_mutation_replaces_all_nodes_and_edges(self):
        """After a mutation the graph must reflect the new state, not a
        mix of old and new rows."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        _call_commit(conn, trip_id, user_id, "graph-create")
        assert _count_rows(conn, "trip_node", trip_id) == 2

        # Mutation: commit again at version 1 (same nodes, different cmd).
        _call_commit(
            conn,
            trip_id,
            user_id,
            "graph-mutate",
            command_type="change_mood",
            payload={"mood": "calm"},
            expected_version=1,
        )
        # Graph must still have exactly 2 nodes and 1 edge (replaced, not doubled).
        assert _count_rows(conn, "trip_node", trip_id) == 2
        assert _count_rows(conn, "trip_edge", trip_id) == 1

        cur = conn.cursor()
        cur.execute("SELECT version FROM trip_states WHERE trip_id = %s::UUID", (trip_id,))
        assert cur.fetchone()[0] == 2
        cur.close()
        conn.close()

    def test_observed_duration_survives_graph_replacement(self):
        """An observed_duration_minutes value recorded on an edge must
        survive the delete-reinsert graph replacement."""
        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        _call_commit(conn, trip_id, user_id, "obs-create")

        # Simulate an observed-duration recording.
        cur = conn.cursor()
        cur.execute(
            dedent("""\
            UPDATE trip_edge
               SET observed_duration_minutes = 17
             WHERE trip_id = %s::UUID
        """),
            (trip_id,),
        )
        conn.commit()
        cur.close()

        # Mutation replaces the graph.
        _call_commit(
            conn,
            trip_id,
            user_id,
            "obs-mutate",
            command_type="change_mood",
            payload={"mood": "fast"},
            expected_version=1,
        )

        cur = conn.cursor()
        cur.execute(
            dedent("""\
            SELECT observed_duration_minutes FROM trip_edge
             WHERE trip_id = %s::UUID
        """),
            (trip_id,),
        )
        row = cur.fetchone()
        assert row is not None and row[0] == 17, "observed duration lost"
        cur.close()
        conn.close()


# =====================================================================
# Proof 6: Privilege guard
# =====================================================================
class TestPrivilege:
    def test_rpc_rejects_non_service_role(self):
        """commit_trip_command must raise when called without
        service_role JWT claim."""
        import psycopg2

        conn = _pg_connect()
        trip_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _ensure_user(conn, user_id)

        cur = conn.cursor()
        # Do NOT set request.jwt.claim.role.
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(
                dedent("""\
                    SELECT commit_trip_command(
                        %s::UUID, %s::UUID, 'priv-test', 'create_trip',
                        %s, NULL,
                        %s::JSONB, '[]'::JSONB, '[]'::JSONB,
                        NULL, NULL, FALSE
                    )
                """),
                (
                    trip_id,
                    user_id,
                    _payload_hash({"kind": "create"}),
                    json.dumps(_state_json(trip_id, user_id)),
                ),
            )
        conn.close()
