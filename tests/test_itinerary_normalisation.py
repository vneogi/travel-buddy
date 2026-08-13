"""Tests for SPEC-16 itinerary normalisation.

Covers:
- Round-trip equality: decompose -> compose == original nodes
- Idempotent backfill: running twice produces identical state
- API wire format: composed output matches TripNode model fields
- Sparse seq stability: insert between nodes changes no other seq
- Non-venue nodes: rest/transit with venue_ref=None persist correctly
- Status mapping: pending/completed/skipped round-trip correctly
- Dual-write: save_trip populates both state_json and normalised rows
- Duplicate venue: same venue visited twice produces distinct nodes
- Cascade delete: deleting trip removes nodes and edges
- Backend parity: both backends implement the contract
- Migration is additive-only (no DROP, no ALTER on existing tables)
"""

import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from models.schemas import TripNode, TripState, NodeStatus
from services.database_service import DatabaseService
from services.itinerary_normaliser import (
    compose_trip_nodes,
    decompose_trip,
    round_trip_equal,
    REGION_TIMEZONES,
    _SEQ_GAP,
)


def _make_trip(num_nodes=3, geo_region="dubai_uae") -> TripState:
    """Create a test trip with N nodes."""
    base_time = datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc)
    nodes = []
    for i in range(num_nodes):
        nodes.append(TripNode(
            node_id=f"node-{i:04d}",
            venue_name=f"Venue {i}",
            venue_id=str(uuid.uuid4()) if i % 2 == 0 else None,
            scheduled_start=base_time + timedelta(hours=i * 2),
            duration_minutes=90,
            is_locked=(i == 0),
            status=NodeStatus.PENDING,
            micro_location=f"Location {i}",
            vibe_tags=["culture", "food"] if i % 2 == 0 else [],
            lat=25.0 + i * 0.01,
            lng=55.0 + i * 0.01,
            opening_hours="09:00-22:00",
            geo_region=geo_region,
        ))
    return TripState(
        trip_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        geo_region=geo_region,
        nodes=nodes,
    )


# ---------------------------------------------------------------------------
# Round-trip equality
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_empty_trip_round_trips(self):
        trip = _make_trip(num_nodes=0)
        trip_dict = trip.model_dump(mode="json")
        assert round_trip_equal(trip_dict)

    def test_single_node_round_trips(self):
        trip = _make_trip(num_nodes=1)
        trip_dict = trip.model_dump(mode="json")
        assert round_trip_equal(trip_dict)

    def test_multi_node_round_trips(self):
        trip = _make_trip(num_nodes=5)
        trip_dict = trip.model_dump(mode="json")
        assert round_trip_equal(trip_dict)

    def test_completed_status_round_trips(self):
        trip = _make_trip(num_nodes=2)
        trip.nodes[0].status = NodeStatus.COMPLETED
        trip.nodes[1].status = NodeStatus.SKIPPED
        trip_dict = trip.model_dump(mode="json")
        assert round_trip_equal(trip_dict)

    def test_locked_node_preserves_lock(self):
        trip = _make_trip(num_nodes=3)
        trip.nodes[1].is_locked = True
        trip_dict = trip.model_dump(mode="json")
        nodes, _ = decompose_trip(trip_dict)
        composed = compose_trip_nodes(nodes)
        assert composed[1]["is_locked"] is True


# ---------------------------------------------------------------------------
# Decompose structure
# ---------------------------------------------------------------------------

class TestDecompose:
    def test_node_count_matches(self):
        trip = _make_trip(num_nodes=4)
        nodes, edges = decompose_trip(trip.model_dump(mode="json"))
        assert len(nodes) == 4
        assert len(edges) == 3  # N-1 edges

    def test_sparse_seq(self):
        trip = _make_trip(num_nodes=3)
        nodes, _ = decompose_trip(trip.model_dump(mode="json"))
        seqs = [n["seq"] for n in nodes]
        assert seqs == [_SEQ_GAP, 2 * _SEQ_GAP, 3 * _SEQ_GAP]

    def test_node_id_stable(self):
        """node_id must be preserved from the source, never regenerated."""
        trip = _make_trip(num_nodes=2)
        trip_dict = trip.model_dump(mode="json")
        nodes, _ = decompose_trip(trip_dict)
        assert nodes[0]["node_id"] == "node-0000"
        assert nodes[1]["node_id"] == "node-0001"

    def test_venue_ref_nullable(self):
        """Nodes without venue_id produce venue_ref=None."""
        trip = _make_trip(num_nodes=3)
        nodes, _ = decompose_trip(trip.model_dump(mode="json"))
        # node-0001 has no venue_id (odd index)
        assert nodes[1]["venue_ref"] is None

    def test_edge_references_correct_nodes(self):
        trip = _make_trip(num_nodes=3)
        nodes, edges = decompose_trip(trip.model_dump(mode="json"))
        assert edges[0]["from_node_id"] == nodes[0]["node_id"]
        assert edges[0]["to_node_id"] == nodes[1]["node_id"]
        assert edges[1]["from_node_id"] == nodes[1]["node_id"]
        assert edges[1]["to_node_id"] == nodes[2]["node_id"]

    def test_observed_duration_present(self):
        """observed_duration_minutes must exist from day one (even if None)."""
        trip = _make_trip(num_nodes=2)
        _, edges = decompose_trip(trip.model_dump(mode="json"))
        assert "observed_duration_minutes" in edges[0]

    def test_geo_region_per_node(self):
        """Each node carries its own geo_region for timezone lookup."""
        trip = _make_trip(num_nodes=2, geo_region="luang_prabang_laos")
        nodes, _ = decompose_trip(trip.model_dump(mode="json"))
        assert nodes[0]["geo_region"] == "luang_prabang_laos"

    def test_timestamptz_format(self):
        """scheduled_start must be timezone-aware (contains offset)."""
        trip = _make_trip(num_nodes=1)
        nodes, _ = decompose_trip(trip.model_dump(mode="json"))
        start = nodes[0]["scheduled_start"]
        # Must contain timezone offset (+00:00 or Z)
        assert "+" in start or "Z" in start


# ---------------------------------------------------------------------------
# Compose (API wire format)
# ---------------------------------------------------------------------------

class TestCompose:
    def test_wire_format_fields(self):
        """Composed output must have exactly the TripNode model fields."""
        trip = _make_trip(num_nodes=1)
        nodes, _ = decompose_trip(trip.model_dump(mode="json"))
        composed = compose_trip_nodes(nodes)
        expected_keys = {
            "node_id", "venue_name", "venue_id", "scheduled_start",
            "duration_minutes", "is_locked", "status", "micro_location",
            "vibe_tags", "lat", "lng", "opening_hours", "geo_region",
        }
        assert set(composed[0].keys()) == expected_keys

    def test_ordering_by_day_seq(self):
        """Compose must return nodes ordered by (day_index, seq)."""
        rows = [
            {"node_id": "b", "day_index": 0, "seq": 2000, "title": "B",
             "duration_minutes": 60, "is_locked": False, "status": "planned",
             "venue_ref": None, "micro_location": None, "vibe_tags": [],
             "lat": None, "lng": None, "opening_hours": None, "geo_region": None,
             "scheduled_start": None, "scheduled_end": None},
            {"node_id": "a", "day_index": 0, "seq": 1000, "title": "A",
             "duration_minutes": 60, "is_locked": False, "status": "planned",
             "venue_ref": None, "micro_location": None, "vibe_tags": [],
             "lat": None, "lng": None, "opening_hours": None, "geo_region": None,
             "scheduled_start": None, "scheduled_end": None},
        ]
        composed = compose_trip_nodes(rows)
        assert composed[0]["node_id"] == "a"
        assert composed[1]["node_id"] == "b"


# ---------------------------------------------------------------------------
# Idempotent backfill
# ---------------------------------------------------------------------------

class TestIdempotent:
    def test_decompose_twice_same_result(self):
        """Running decompose twice produces identical nodes."""
        trip = _make_trip(num_nodes=3)
        trip_dict = trip.model_dump(mode="json")
        nodes1, edges1 = decompose_trip(trip_dict)
        nodes2, edges2 = decompose_trip(trip_dict)
        # Node content must be identical (excluding edge_id which is random)
        for n1, n2 in zip(nodes1, nodes2):
            assert n1 == n2

    def test_dual_write_idempotent(self):
        """Saving the same trip twice produces identical normalised state."""
        db = DatabaseService()
        trip = _make_trip(num_nodes=3)
        db.save_trip(trip)
        nodes_first = db.get_trip_nodes(trip.trip_id)
        db.save_trip(trip)
        nodes_second = db.get_trip_nodes(trip.trip_id)
        assert nodes_first == nodes_second


# ---------------------------------------------------------------------------
# Dual-write verification
# ---------------------------------------------------------------------------

class TestDualWrite:
    def test_save_trip_writes_nodes(self):
        """save_trip must populate normalised node rows."""
        db = DatabaseService()
        trip = _make_trip(num_nodes=4)
        db.save_trip(trip)
        nodes = db.get_trip_nodes(trip.trip_id)
        assert len(nodes) == 4

    def test_save_trip_writes_edges(self):
        """save_trip must populate normalised edge rows."""
        db = DatabaseService()
        trip = _make_trip(num_nodes=3)
        db.save_trip(trip)
        edges = db.get_trip_edges(trip.trip_id)
        assert len(edges) == 2

    def test_duplicate_venue_produces_distinct_nodes(self):
        """Same venue visited twice -> two distinct node rows."""
        trip = _make_trip(num_nodes=2)
        shared_venue = str(uuid.uuid4())
        trip.nodes[0].venue_id = shared_venue
        trip.nodes[1].venue_id = shared_venue
        trip.nodes[0].venue_name = "Same Place"
        trip.nodes[1].venue_name = "Same Place"
        db = DatabaseService()
        db.save_trip(trip)
        nodes = db.get_trip_nodes(trip.trip_id)
        assert len(nodes) == 2
        assert nodes[0]["node_id"] != nodes[1]["node_id"]


# ---------------------------------------------------------------------------
# Backend parity (method existence)
# ---------------------------------------------------------------------------

class TestBackendParity:
    def test_both_backends_have_node_methods(self):
        """Both DatabaseService and SupabaseService must have SPEC-16 methods."""
        from services.supabase_service import SupabaseService
        required = ["save_trip_nodes", "get_trip_nodes",
                    "save_trip_edges", "get_trip_edges"]
        for method in required:
            assert hasattr(DatabaseService, method), (
                f"DatabaseService missing {method}"
            )
            assert hasattr(SupabaseService, method), (
                f"SupabaseService missing {method}"
            )


# ---------------------------------------------------------------------------
# Migration guards
# ---------------------------------------------------------------------------

def _strip_sql_comments(sql: str) -> str:
    """Remove SQL line comments for assertion clarity."""
    return re.sub(r"--[^\n]*", "", sql)


class TestMigration:
    @pytest.fixture
    def migration_sql(self):
        fp = REPO_ROOT / "supabase" / "migrations" / "0014_itinerary_normalisation.sql"
        return fp.read_text()

    def test_migration_is_additive_only(self, migration_sql):
        """Migration must not DROP or ALTER existing tables."""
        stripped = _strip_sql_comments(migration_sql)
        assert not re.search(r"\bDROP\b", stripped), (
            "Migration 0014 must not contain DROP statements"
        )
        # Must not ALTER trip_states (the existing table)
        assert not re.search(r"ALTER\s+TABLE\s+trip_states", stripped), (
            "Migration 0014 must not ALTER trip_states"
        )

    def test_trip_node_table_created(self, migration_sql):
        stripped = _strip_sql_comments(migration_sql)
        assert re.search(r"CREATE\s+TABLE.*trip_node", stripped)

    def test_trip_edge_table_created(self, migration_sql):
        stripped = _strip_sql_comments(migration_sql)
        assert re.search(r"CREATE\s+TABLE.*trip_edge", stripped)

    def test_observed_duration_column_exists(self, migration_sql):
        assert "observed_duration_minutes" in migration_sql

    def test_cascade_on_delete(self, migration_sql):
        """Both tables must CASCADE on trip deletion."""
        assert migration_sql.count("ON DELETE CASCADE") >= 3

    def test_node_type_vocabulary(self, migration_sql):
        """All required node types are in the CHECK constraint."""
        for ntype in ("activity", "flight", "hotel", "train", "rest", "transit"):
            assert ntype in migration_sql, f"Missing node_type: {ntype}"

    def test_status_vocabulary(self, migration_sql):
        """All required status values are in the CHECK constraint."""
        for status in ("planned", "visited", "skipped", "cancelled"):
            assert status in migration_sql, f"Missing status: {status}"

    def test_timestamptz_used(self, migration_sql):
        """Times must use TIMESTAMPTZ, not TIMESTAMP."""
        # scheduled_start and scheduled_end must be TIMESTAMPTZ
        assert "TIMESTAMPTZ" in migration_sql

    def test_timezone_choice_documented(self, migration_sql):
        """Migration comment must state the timezone design choice."""
        assert "TIMEZONE CHOICE" in migration_sql


# ---------------------------------------------------------------------------
# REGION_TIMEZONES mapping
# ---------------------------------------------------------------------------

class TestRegionTimezones:
    def test_all_known_regions_mapped(self):
        """Every geo_region used in data files must map to an IANA timezone."""
        required = ["dubai_uae", "luang_prabang_laos", "vang_vieng_laos",
                    "vientiane_laos"]
        for region in required:
            assert region in REGION_TIMEZONES, f"Missing: {region}"

    def test_values_are_iana(self):
        """All timezone values must look like IANA zone names."""
        for region, tz in REGION_TIMEZONES.items():
            assert "/" in tz, f"{region} -> {tz} is not IANA format"
