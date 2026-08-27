from datetime import datetime, timezone
from pathlib import Path

from agents.state_machine import TripStateMachine
from models.schemas import VenueRAG

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_venue_model_and_trip_node_preserve_driver_card_fields():
    venue = VenueRAG(
        venue_id="wat-xieng-thong",
        name="Wat Xieng Thong",
        description="Temple",
        micro_location="Luang Prabang",
        lat=19.8976,
        lng=102.1432,
        geo_region="luang_prabang_laos",
        names_local={"lo": {"value": "Lao name", "source": "osm"}},
        landmarks_local={"lo": {"value": "Lao landmark", "source": "osm"}},
        nearest_landmark="Near the Mekong",
    )

    node = TripStateMachine._node_from_venue(
        venue,
        datetime(2026, 10, 4, tzinfo=timezone.utc),
        90,
        "node-1",
    )

    assert node.geo_region == "luang_prabang_laos"
    assert node.names_local == venue.names_local
    assert node.landmarks_local == venue.landmarks_local
    assert node.nearest_landmark == "Near the Mekong"


def test_live_search_migration_returns_driver_card_fields_and_region_filter():
    sql = (
        REPO_ROOT / "supabase" / "migrations" / "0023_driver_card_search_fields.sql"
    ).read_text(encoding="utf-8")

    for field in (
        "filter_geo_region",
        "geo_region",
        "names_local",
        "landmarks_local",
        "nearest_landmark",
    ):
        assert field in sql
