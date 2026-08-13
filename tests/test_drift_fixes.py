"""Tests for migration 0015 drift fixes.

Guards assert on what the PRODUCTION PATH emits, not on test helpers.
- Fix A: venue_dish.price_band CHECK == taxonomy_term price_band seed
- Fix B: No dish loses its local name; names_local JSONB written on production path
- Fix C: Every priced dish row has a currency_code on the production path
- Fix D: No embedding written without a model tag on the production path
"""

import json
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from load_venues import (
    EMBEDDING_MODEL,
    REGION_CURRENCIES,
    REGION_LANGUAGES,
    VENUES_RAG_WRITE_COLUMNS,
    build_venue_record,
)

DATA_DIR = REPO_ROOT / "data"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


# ---------------------------------------------------------------------------
# Fix A: price_band CHECK == taxonomy seed (sabotage-ready)
# ---------------------------------------------------------------------------

def _extract_check_terms_from_0015() -> set:
    """Extract the price_band CHECK term set from migration 0015."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    stripped = _strip_sql_comments(sql)
    # Find the ADD CONSTRAINT line with the CHECK
    match = re.search(
        r"ADD\s+CONSTRAINT\s+venue_dish_price_band_check\s+CHECK\s*\("
        r"price_band\s+IN\s*\(([^)]+)\)",
        stripped,
    )
    assert match, "Could not find price_band CHECK in 0015"
    raw = match.group(1)
    terms = set(re.findall(r"'([^']+)'", raw))
    return terms


def _extract_seed_price_band_terms() -> set:
    """Extract price_band terms from taxonomy_term seed in 0013."""
    sql = (MIGRATIONS_DIR / "0013_taxonomy_term.sql").read_text()
    terms = set(re.findall(r"'price_band',\s*'([^']+)'", sql))
    return terms


def test_price_band_check_equals_taxonomy_seed():
    """The 0015 CHECK term set must exactly equal the taxonomy_term price_band seed."""
    check_terms = _extract_check_terms_from_0015()
    seed_terms = _extract_seed_price_band_terms()
    assert check_terms == seed_terms, (
        f"CHECK terms {sorted(check_terms)} != seed terms {sorted(seed_terms)}"
    )


def test_price_band_check_no_premium():
    """The old 'premium' term must NOT appear in the new CHECK."""
    check_terms = _extract_check_terms_from_0015()
    assert "premium" not in check_terms, "'premium' still in CHECK"


def test_price_band_check_has_free():
    """The new CHECK must include 'free' from the taxonomy seed."""
    check_terms = _extract_check_terms_from_0015()
    assert "free" in check_terms, "'free' missing from CHECK"


# ---------------------------------------------------------------------------
# Fix B: Dish localisation — production path writes names_local
# ---------------------------------------------------------------------------

class FakeInsertChain:
    """Captures the insert payload from a Supabase-style fluent call."""
    def __init__(self, store):
        self._store = store

    def insert(self, data):
        self._store.append(data)
        return self

    def delete(self):
        return self

    def eq(self, *a):
        return self

    def execute(self):
        class R:
            data = []
        return R()


def _run_production_dish_insert(venue_data: dict, geo_region: str) -> list:
    """Simulate the production dish-insert path via the loader, capturing payloads."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import importlib
    import load_venues as lv
    importlib.reload(lv)
    sys.path.pop(0)

    captured = []

    class FakeTable:
        def __init__(self, name):
            self._name = name
        def insert(self, data):
            if self._name == "venue_dish":
                captured.append(data)
            return self
        def delete(self):
            return self
        def eq(self, *a):
            return self
        def select(self, *a):
            return self
        def upsert(self, data, **kw):
            return self
        def order(self, *a, **kw):
            return self
        def execute(self):
            class R:
                data = []
            return R()

    class FakeClient:
        def table(self, name):
            return FakeTable(name)

    import types
    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda url, key: FakeClient()

    import os
    old_env = os.environ.copy()
    os.environ["TB_SUPABASE_URL"] = "http://fake"
    os.environ["TB_SUPABASE_KEY"] = "fake"
    sys.modules["supabase"] = fake_supabase

    importlib.reload(lv)

    # Call the production path
    fake_embeddings = [[0.0] * 3]
    lv.upsert_venues([venue_data], geo_region, fake_embeddings)

    os.environ.clear()
    os.environ.update(old_env)
    del sys.modules["supabase"]

    return captured


def test_dish_names_local_written_on_production_path():
    """Production path must write names_local JSONB for dishes with name_local."""
    # Load a real venue with dishes
    data = json.loads((DATA_DIR / "laos_luang_prabang.json").read_text())
    venue = next(v for v in data["venues"] if v.get("dishes"))

    captured = _run_production_dish_insert(venue, "luang_prabang_laos")
    assert len(captured) > 0, "No dish inserts captured"

    for payload in captured:
        if payload.get("name_local"):
            assert payload.get("names_local") is not None, (
                f"Dish '{payload.get('name_en')}' has name_local but no names_local JSONB"
            )
            nl = payload["names_local"]
            assert "lo" in nl, "names_local missing 'lo' key"
            assert nl["lo"]["value"] == payload["name_local"]
            assert nl["lo"]["source"] == "generated"


def test_no_dish_loses_local_name():
    """Every dish with name_local in data must still have it in the payload."""
    data = json.loads((DATA_DIR / "laos_luang_prabang.json").read_text())
    venue = next(v for v in data["venues"] if v.get("dishes"))
    dishes_with_local = [d for d in venue["dishes"] if d.get("name_local")]

    captured = _run_production_dish_insert(venue, "luang_prabang_laos")

    captured_locals = [p["name_local"] for p in captured if p.get("name_local")]
    for d in dishes_with_local:
        assert d["name_local"] in captured_locals, (
            f"Dish name_local lost: {d.get('name_local')[:20]}"
        )


# ---------------------------------------------------------------------------
# Fix C: Currency — every priced row has currency_code on production path
# ---------------------------------------------------------------------------

def test_every_priced_dish_has_currency():
    """Production path: if price_local is set, currency_code must be set."""
    data = json.loads((DATA_DIR / "laos_luang_prabang.json").read_text())
    venue = next(v for v in data["venues"] if v.get("dishes") and
                 any(d.get("price_local") for d in v["dishes"]))

    captured = _run_production_dish_insert(venue, "luang_prabang_laos")

    priced = [p for p in captured if p.get("price_local")]
    assert len(priced) > 0, "No priced dishes found"
    for payload in priced:
        assert payload.get("currency_code") is not None, (
            f"Dish '{payload.get('name_en')}' has price_local={payload['price_local']} "
            f"but no currency_code"
        )
        assert payload["currency_code"] == "LAK"


def test_unpriced_dish_has_no_currency():
    """Unpriced dishes must NOT have a spurious currency_code."""
    data = json.loads((DATA_DIR / "laos_luang_prabang.json").read_text())
    # Find a venue with at least one unpriced dish
    for v in data["venues"]:
        if v.get("dishes") and any(not d.get("price_local") for d in v["dishes"]):
            captured = _run_production_dish_insert(v, "luang_prabang_laos")
            unpriced = [p for p in captured if not p.get("price_local")]
            for payload in unpriced:
                assert payload.get("currency_code") is None
            return
    pytest.skip("No unpriced dishes found in test data")


def test_region_currencies_covers_all_regions():
    """Every REGION_LANGUAGES region must have a REGION_CURRENCIES entry."""
    for region in REGION_LANGUAGES:
        assert region in REGION_CURRENCIES, f"No currency for region: {region}"


# ---------------------------------------------------------------------------
# Fix D: Embedding provenance — production path tags every embedding
# ---------------------------------------------------------------------------

def test_embedding_model_in_write_columns():
    """VENUES_RAG_WRITE_COLUMNS must include embedding_model."""
    assert "embedding_model" in VENUES_RAG_WRITE_COLUMNS


def test_build_venue_record_includes_embedding_model():
    """Production path: build_venue_record must set embedding_model."""
    # Use a minimal venue dict
    venue = {
        "name": "Test Venue",
        "description": "A test",
        "micro_location": "loc",
        "lat": 25.0,
        "lng": 55.0,
        "category": "restaurant",
    }
    record = build_venue_record(venue, str(uuid.uuid4()), [0.1] * 3, "dubai_uae")
    assert record.get("embedding_model") is not None, (
        "build_venue_record did not set embedding_model"
    )
    assert record["embedding_model"] == EMBEDDING_MODEL


def test_embedding_model_constant_is_nonempty():
    """EMBEDDING_MODEL must be a non-empty string."""
    assert isinstance(EMBEDDING_MODEL, str) and len(EMBEDDING_MODEL) > 0


# ---------------------------------------------------------------------------
# Migration structure guards
# ---------------------------------------------------------------------------

def test_migration_0015_drops_old_check():
    """0015 must DROP the old constraint."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    assert "DROP CONSTRAINT" in sql


def test_migration_0015_adds_names_local():
    """0015 must ADD names_local JSONB."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    assert "names_local" in sql and "JSONB" in sql


def test_migration_0015_adds_currency_code():
    """0015 must ADD currency_code."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    assert "currency_code" in sql


def test_migration_0015_adds_embedding_model():
    """0015 must ADD embedding_model to both tables."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    assert sql.count("embedding_model") >= 2


def test_migration_0015_marks_aed_suspect():
    """0015 comment must flag AED rows as suspect."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    assert "suspect" in sql.lower() or "device-check" in sql.lower()
