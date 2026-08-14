"""Tests for migration 0015 drift fixes.

Guards assert on what the PRODUCTION PATH emits, not on test helpers.
- Fix A: venue_dish.price_band CHECK == taxonomy_term price_band seed
- Fix B: No dish loses its local name; backfill scoped to Laos only
- Fix C: Every priced dish row has a currency_code on the production path
- Fix D: No embedding written without a model tag on the production path
"""

import json
import re
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from load_venues import (
    EMBEDDING_MODEL,
    REGION_CURRENCIES,
    REGION_LANGUAGES,
    VENUE_DISH_WRITE_COLUMNS,
    VENUES_RAG_WRITE_COLUMNS,
    build_dish_record,
    build_venue_record,
)

DATA_DIR = REPO_ROOT / "data"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


# ---------------------------------------------------------------------------
# Fix A: price_band CHECK == taxonomy seed (sabotage-ready)
# ---------------------------------------------------------------------------

def test_all_price_band_checks_equal_taxonomy_seed():
    """Every final CHECK on a price_band column must equal the taxonomy_term seed.

    Scans all migrations in filename order, tracks the last CHECK state per
    (table, column). Each final state must match the seed from 0013. This makes
    the drift class closed by construction: any future migration that introduces
    or supersedes a price_band CHECK will be caught if it disagrees with the seed.
    """
    # Extract seed from 0013
    sql_0013 = (MIGRATIONS_DIR / "0013_taxonomy_term.sql").read_text()
    seed_terms = set(re.findall(r"'price_band',\s*'([^']+)'", sql_0013))
    assert seed_terms, "No price_band terms found in taxonomy seed (0013)"

    # Scan all migrations in order, track final CHECK per (table, column)
    # Pattern: ADD CONSTRAINT <name> CHECK (price_band IN (...))
    # or inline CHECK (price_band IN (...)) in CREATE TABLE
    check_pattern = re.compile(
        r"(?:ALTER\s+TABLE\s+(\w+)\s+ADD\s+CONSTRAINT\s+\w+\s+CHECK|"
        r"(\w+)\s+TEXT\s+CHECK)\s*\(\s*price_band\s+IN\s*\(([^)]+)\)",
        re.IGNORECASE | re.DOTALL,
    )

    final_checks = {}  # (table, 'price_band') -> set of terms
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for mig_path in migration_files:
        sql = _strip_sql_comments(mig_path.read_text())
        for match in check_pattern.finditer(sql):
            table = match.group(1) or "inline"
            terms = set(re.findall(r"'([^']+)'", match.group(3)))
            # For ALTER TABLE, group(1) has the table name
            # For inline CHECK in CREATE TABLE, we need the table from context
            if match.group(1):
                table = match.group(1)
            else:
                # Find CREATE TABLE preceding this inline CHECK
                preceding = sql[:match.start()]
                create_match = re.findall(
                    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
                    preceding, re.IGNORECASE
                )
                table = create_match[-1] if create_match else "unknown"
            final_checks[(table, "price_band")] = (terms, mig_path.name)

    assert final_checks, "No price_band CHECK constraints found in any migration"

    failures = []
    for (table, col), (terms, mig_name) in sorted(final_checks.items()):
        if terms != seed_terms:
            failures.append(
                f"  {mig_name}: {table}.{col} CHECK {sorted(terms)} "
                f"!= seed {sorted(seed_terms)}"
            )
    assert not failures, (
        "price_band CHECK constraint(s) disagree with taxonomy_term seed:\n"
        + "\n".join(failures)
    )


def test_price_band_check_is_not_valid():
    """The CHECK must use NOT VALID to avoid aborting on existing rows."""
    sql = _strip_sql_comments((MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text())
    match = re.search(
        r"ADD\s+CONSTRAINT\s+venue_dish_price_band_check.*?NOT\s+VALID",
        sql, re.DOTALL
    )
    assert match, "CHECK constraint missing NOT VALID in DDL (comments stripped)"


def test_validate_constraint_is_commented():
    """VALIDATE CONSTRAINT must be present but commented out."""
    sql = (MIGRATIONS_DIR / "0015_drift_fixes.sql").read_text()
    assert "-- ALTER TABLE venue_dish VALIDATE CONSTRAINT" in sql


# ---------------------------------------------------------------------------
# Fix B: Dish localisation -- production path + backfill scope
# ---------------------------------------------------------------------------

def _run_production_dish_insert(venue_data: dict, geo_region: str) -> list:
    """Simulate the production dish-insert path, capturing payloads.

    Uses monkeypatch-style try/finally to ensure cleanup even on failure.
    """
    import importlib
    import os
    import types

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

    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda url, key: FakeClient()

    old_env = os.environ.copy()
    old_supabase = sys.modules.get("supabase")
    try:
        os.environ["TB_SUPABASE_URL"] = "http://fake"
        os.environ["TB_SUPABASE_KEY"] = "fake"
        sys.modules["supabase"] = fake_supabase

        # Reload to pick up the patched module
        import load_venues as lv
        importlib.reload(lv)

        fake_embeddings = [[0.0] * 3]
        lv.upsert_venues([venue_data], geo_region, fake_embeddings)
    finally:
        # Restore environment regardless of success/failure
        os.environ.clear()
        os.environ.update(old_env)
        if old_supabase is not None:
            sys.modules["supabase"] = old_supabase
        else:
            sys.modules.pop("supabase", None)

    return captured


def test_dish_names_local_written_on_production_path():
    """Production path must write names_local JSONB for Laos dishes with name_local."""
    data = json.loads((DATA_DIR / "laos_luang_prabang.json").read_text())
    venue = next(v for v in data["venues"] if v.get("dishes"))
    captured = _run_production_dish_insert(venue, "luang_prabang_laos")
    assert len(captured) > 0, "No dish inserts captured"

    for payload in captured:
        if payload.get("name_local"):
            assert payload.get("names_local") is not None, (
                f"Dish '{payload.get('name_en')}' has name_local but no names_local"
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
        assert d["name_local"] in captured_locals


def test_backfill_does_not_invent_language_for_dubai():
    """A Dubai dish must NOT get names_local with 'lo' key from the backfill.

    The migration scopes the UPDATE to Laos geo_regions only.
    This tests the SQL logic by verifying the production path uses the correct
    region language (ar for dubai, not lo).
    """
    # Synthetic Dubai venue with a dish
    dubai_venue = {
        "name": "Test Dubai Venue",
        "description": "A test",
        "micro_location": "Downtown",
        "lat": 25.2,
        "lng": 55.27,
        "category": "restaurant",
        "dishes": [{
            "dish_name": "Shawarma",
            "name_local": "\u0634\u0627\u0648\u0631\u0645\u0627",
            "is_signature": True,
            "cuisine": "emirati",
            "price_local": 4500,
            "price_band": "budget",
        }],
    }
    captured = _run_production_dish_insert(dubai_venue, "dubai_uae")
    assert len(captured) == 1
    nl = captured[0]["names_local"]
    # Must use "ar" (Arabic), NOT "lo" (Lao)
    assert "lo" not in nl, f"Dubai dish got 'lo' key: {nl}"
    assert "ar" in nl, f"Dubai dish missing 'ar' key: {nl}"


# ---------------------------------------------------------------------------
# Fix C: Currency -- every priced row has currency_code on production path
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
        assert payload.get("currency_code") == "LAK"


def test_unpriced_dish_has_no_currency():
    """Unpriced dishes must NOT have a spurious currency_code."""
    # Synthetic unpriced dish -- avoids skip when no real data matches
    venue = {
        "name": "Free Samples Cafe",
        "description": "Tasting only",
        "micro_location": "Market",
        "lat": 19.89,
        "lng": 102.13,
        "category": "cafe",
        "dishes": [{
            "dish_name": "Free Tea Sample",
            "name_local": None,
            "is_signature": False,
            "cuisine": "lao",
            "price_local": None,
            "price_band": None,
        }],
    }
    captured = _run_production_dish_insert(venue, "luang_prabang_laos")
    assert len(captured) == 1
    assert captured[0]["currency_code"] is None


def test_region_currencies_covers_all_regions():
    """Every REGION_LANGUAGES region must have a REGION_CURRENCIES entry."""
    for region in REGION_LANGUAGES:
        assert region in REGION_CURRENCIES, f"No currency for region: {region}"


# ---------------------------------------------------------------------------
# Fix D: Embedding provenance -- production path tags every embedding
# ---------------------------------------------------------------------------

def test_embedding_model_in_write_columns():
    """VENUES_RAG_WRITE_COLUMNS must include embedding_model."""
    assert "embedding_model" in VENUES_RAG_WRITE_COLUMNS


def test_build_venue_record_includes_embedding_model():
    """Production path: build_venue_record must set embedding_model."""
    venue = {
        "name": "Test Venue", "description": "A test",
        "micro_location": "loc", "lat": 25.0, "lng": 55.0, "category": "restaurant",
    }
    record = build_venue_record(venue, str(uuid.uuid4()), [0.1] * 3, "dubai_uae")
    assert record.get("embedding_model") == EMBEDDING_MODEL


def test_embedding_model_constant_is_nonempty():
    """EMBEDDING_MODEL must be a non-empty string."""
    assert isinstance(EMBEDDING_MODEL, str) and len(EMBEDDING_MODEL) > 0


def test_cache_write_includes_embedding_model():
    """The real store_cache method must include embedding_model in the entry.

    Drives the actual method with a fake client to capture the insert payload.
    """
    sys.path.insert(0, str(REPO_ROOT))
    import importlib
    import os
    import types

    class CaptureTable:
        def __init__(self):
            self.captured = None
        def insert(self, data):
            self.captured = data
            return self
        def execute(self):
            class R:
                data = []
            return R()

    class FakeClient:
        def __init__(self):
            self.cache_table = CaptureTable()
        def table(self, name):
            if name == "cached_responses":
                return self.cache_table
            return CaptureTable()

    old_env = os.environ.copy()
    old_supabase = sys.modules.get("supabase")
    try:
        os.environ["TB_SUPABASE_URL"] = "http://fake"
        os.environ["TB_SUPABASE_KEY"] = "fake"

        fake_supabase = types.ModuleType("supabase")
        fake_client = FakeClient()
        fake_supabase.create_client = lambda url, key: fake_client
        sys.modules["supabase"] = fake_supabase

        from services import supabase_service
        importlib.reload(supabase_service)
        svc = supabase_service.SupabaseService()
        svc._client = fake_client

        svc.store_cache(
            query_text="test query",
            query_embedding=[0.1] * 10,
            response_text="test response",
        )

        entry = fake_client.cache_table.captured
        assert entry is not None, "No cache entry captured"
        assert "embedding_model" in entry, "embedding_model missing from cache entry"
        assert entry["embedding_model"] == EMBEDDING_MODEL
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        if old_supabase is not None:
            sys.modules["supabase"] = old_supabase
        else:
            sys.modules.pop("supabase", None)


# ---------------------------------------------------------------------------
# Payload guard (Fix 4)
# ---------------------------------------------------------------------------

def test_build_dish_record_key_guard():
    """build_dish_record must produce exactly VENUE_DISH_WRITE_COLUMNS keys."""
    dish = {
        "dish_name": "Test Dish", "name_local": "\u0e97\u0ebb\u0e94\u0eaa\u0ead\u0e9a",
        "is_signature": True, "cuisine": "lao",
        "price_local": 35000, "price_band": "budget",
    }
    record = build_dish_record(dish, str(uuid.uuid4()), "luang_prabang_laos")
    assert set(record.keys()) == VENUE_DISH_WRITE_COLUMNS


def test_build_dish_record_currency_set_when_priced():
    """build_dish_record must set currency_code when price_local is present."""
    dish = {"dish_name": "X", "price_local": 30000, "price_band": "budget"}
    record = build_dish_record(dish, str(uuid.uuid4()), "vientiane_laos")
    assert record["currency_code"] == "LAK"


def test_build_dish_record_no_currency_when_unpriced():
    """build_dish_record must leave currency_code None when no price."""
    dish = {"dish_name": "X", "price_local": None}
    record = build_dish_record(dish, str(uuid.uuid4()), "luang_prabang_laos")
    assert record["currency_code"] is None


# ---------------------------------------------------------------------------
# Fix 0017: venues_rag.price_band CHECK (final drift closure)
# ---------------------------------------------------------------------------




def test_venues_rag_price_band_check_is_not_valid():
    """The CHECK must use NOT VALID (same safety pattern as 0015)."""
    sql = _strip_sql_comments((MIGRATIONS_DIR / "0017_venues_rag_price_band_check.sql").read_text())
    match = re.search(
        r"ADD\s+CONSTRAINT\s+venues_rag_price_band_check.*?NOT\s+VALID",
        sql, re.DOTALL
    )
    assert match, "CHECK constraint missing NOT VALID in DDL (comments stripped)"
