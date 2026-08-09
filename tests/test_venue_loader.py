"""Tests for scripts/load_venues.py — validation logic.

Runs the loader in --dry-run mode against test fixtures.
Asserts exit code and error messages.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(PROJECT_ROOT / "scripts" / "load_venues.py")
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


def run_loader(*files: str, geo_region: str = "luang_prabang_laos") -> subprocess.CompletedProcess:
    """Run load_venues.py --dry-run on given fixture files."""
    cmd = [sys.executable, SCRIPT, "--dry-run", "--geo-region", geo_region]
    cmd.extend(str(FIXTURES / f) for f in files)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))


class TestValidFile:
    def test_valid_passes(self):
        result = run_loader("venues_valid.json")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "VALIDATION PASSED" in result.stdout
        assert "--dry-run: No data written" in result.stdout


class TestInvalidCategory:
    def test_rejects_bad_category(self):
        result = run_loader("venues_invalid_category.json")
        assert result.returncode != 0
        assert "category" in result.stderr.lower()
        assert "nightclub" in result.stderr


class TestInvalidVibeTag:
    def test_rejects_bad_vibe_tag(self):
        result = run_loader("venues_invalid_vibe_tag.json")
        assert result.returncode != 0
        assert "vibe_tag" in result.stderr.lower()
        assert "nonexistent_vibe" in result.stderr


class TestInvalidLat:
    def test_rejects_out_of_bounds_lat(self):
        result = run_loader("venues_invalid_lat.json")
        assert result.returncode != 0
        assert "lat" in result.stderr.lower()
        assert "5.0" in result.stderr


class TestInvalidHours:
    def test_rejects_missing_day_keys(self):
        result = run_loader("venues_invalid_hours.json")
        assert result.returncode != 0
        assert "missing days" in result.stderr.lower() or "missing" in result.stderr.lower()


class TestInvalidTimeRange:
    def test_rejects_end_before_start(self):
        result = run_loader("venues_invalid_time_range.json")
        assert result.returncode != 0
        assert "<=" in result.stderr or "end" in result.stderr.lower()


class TestDuplicateName:
    def test_rejects_duplicate_within_region(self):
        result = run_loader("venues_invalid_duplicate.json")
        assert result.returncode != 0
        assert "duplicate" in result.stderr.lower()


class TestDishOnNonFood:
    def test_rejects_dish_on_temple(self):
        result = run_loader("venues_invalid_dish_on_nonfood.json")
        assert result.returncode != 0
        assert "food category" in result.stderr.lower() or "not a food" in result.stderr.lower()


class TestInvalidCuisine:
    def test_rejects_bad_cuisine(self):
        result = run_loader("venues_invalid_cuisine.json")
        assert result.returncode != 0
        assert "cuisine" in result.stderr.lower()
        assert "martian" in result.stderr


class TestMissingFields:
    def test_rejects_missing_required(self):
        result = run_loader("venues_invalid_missing_fields.json")
        assert result.returncode != 0
        assert "missing" in result.stderr.lower()


class TestUnregisteredRegion:
    def test_rejects_unregistered_geo_region(self):
        result = run_loader("venues_valid.json", geo_region="atlantis_ocean")
        assert result.returncode != 0
        assert "atlantis_ocean" in result.stderr
        assert "not registered" in result.stderr.lower() or "not in" in result.stderr.lower()


class TestTripNodeBackwardCompat:
    """Prove that pre-#80 trip JSON (no geo_region on node) deserializes."""

    def test_pre_80_trip_node_deserializes(self):
        from models.schemas import TripNode

        # A node dict as it would appear in a trip saved before commit #80
        old_node = {
            "node_id": "abc12345",
            "venue_name": "Gold Souk",
            "scheduled_start": "2024-03-15T10:00:00",
            "duration_minutes": 90,
            "is_locked": False,
            "status": "pending",
            "micro_location": "Deira",
            "vibe_tags": ["cultural", "authentic"],
            "lat": 25.2866,
            "lng": 55.2969,
            "opening_hours": "09:00-22:00",
        }
        node = TripNode(**old_node)
        # geo_region defaults to None (not a required field)
        assert node.geo_region is None
        assert node.venue_name == "Gold Souk"

    def test_node_with_explicit_geo_region(self):
        from models.schemas import TripNode

        node = TripNode(
            venue_name="Vang Vieng Riverside",
            scheduled_start="2024-06-01T09:00:00",
            geo_region="vang_vieng_laos",
        )
        assert node.geo_region == "vang_vieng_laos"
