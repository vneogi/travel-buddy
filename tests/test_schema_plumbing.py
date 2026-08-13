"""Tests for schema plumbing: venue_external_id and taxonomy_term.

These tests validate:
1. venue_external_id seed data from the verification artifact
2. venue_external_id writer (build_external_id_record) produces correct rows
3. taxonomy_term seed completeness against venue and glossary data
4. Bidirectional agreement between Python constants and the migration seed
5. Migration safety: additive-only (no DROP, no ALTER venues_rag)
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
DATA_DIR = REPO_ROOT / "data"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from load_venues import (  # noqa: E402
    EXTERNAL_ID_SOURCES,
    TAXONOMY_TERMS,
    VENUE_EXTERNAL_ID_WRITE_COLUMNS,
    build_external_id_record,
    build_venue_record,
)

sys.path.pop(0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_verification_artifact():
    path = DATA_DIR / "laos_name_verification.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_laos_venues():
    """Yield (json_file, geo_region, venue) for the three Laos venue files."""
    for json_file in sorted(DATA_DIR.glob("laos_*.json")):
        if json_file.name in ("laos_dish_glossary.json", "laos_name_verification.json"):
            continue
        data = json.loads(json_file.read_text(encoding="utf-8"))
        venues = data.get("venues", data if isinstance(data, list) else [])
        geo_region = data.get("geo_region", json_file.stem)
        for venue in venues:
            yield json_file, geo_region, venue


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL single-line comments (-- ...) from content."""
    return "\n".join(
        line for line in sql.splitlines()
        if not line.strip().startswith("--")
    )


def _parse_taxonomy_seed_from_migration():
    """Parse the INSERT statements in 0013 to extract seeded (taxonomy, term) pairs."""
    migration = MIGRATIONS_DIR / "0013_taxonomy_term.sql"
    content = migration.read_text(encoding="utf-8")
    pattern = re.compile(r"\('([^']+)',\s*'([^']+)'\)")
    pairs = set()
    for m in pattern.finditer(content):
        pairs.add((m.group(1), m.group(2)))
    return pairs


# ---------------------------------------------------------------------------
# PART 1: venue_external_id
# ---------------------------------------------------------------------------

def test_verification_artifact_has_ten_refs():
    """The verification artifact must carry exactly 10 verified entries with refs."""
    artifact = _load_verification_artifact()
    verified = artifact["verified_names"]
    assert len(verified) == 10, f"Expected 10 verified, got {len(verified)}"
    for entry in verified:
        assert "ref" in entry and entry["ref"], f"Missing ref for {entry['venue_name']}"
        assert "source" in entry and entry["source"], f"Missing source for {entry['venue_name']}"


def test_external_id_sources_are_valid():
    """All sources in the verification artifact must be in EXTERNAL_ID_SOURCES."""
    artifact = _load_verification_artifact()
    for entry in artifact["verified_names"]:
        assert entry["source"] in EXTERNAL_ID_SOURCES, (
            f"Source '{entry['source']}' for {entry['venue_name']} "
            f"not in EXTERNAL_ID_SOURCES: {sorted(EXTERNAL_ID_SOURCES)}"
        )


def test_refs_parse_into_resolvable_form():
    """Each ref must parse into a form that can be resolved against its source.

    Wikidata: Q followed by digits (e.g. Q2671118)
    OSM: type/id where type is node|way|relation and id is digits
    """
    artifact = _load_verification_artifact()
    wikidata_re = re.compile(r"^Q\d+$")
    osm_re = re.compile(r"^(node|way|relation)/\d+$")

    for entry in artifact["verified_names"]:
        source = entry["source"]
        ref = entry["ref"]
        if source == "wikidata":
            assert wikidata_re.match(ref), (
                f"Wikidata ref '{ref}' for {entry['venue_name']} "
                f"does not match Q<digits> pattern"
            )
        elif source == "osm":
            assert osm_re.match(ref), (
                f"OSM ref '{ref}' for {entry['venue_name']} "
                f"does not match type/id pattern"
            )
        else:
            raise AssertionError(f"Unhandled source '{source}' for {entry['venue_name']}")


def test_unique_constraint_on_source_external_id():
    """Migration 0012 must declare UNIQUE(source, external_id) in SQL (not just comments)."""
    migration = MIGRATIONS_DIR / "0012_venue_external_id.sql"
    sql = _strip_sql_comments(migration.read_text(encoding="utf-8"))
    assert re.search(r"UNIQUE\s*\(\s*source\s*,\s*external_id\s*\)", sql), (
        "Migration 0012 must have UNIQUE(source, external_id) constraint "
        "in SQL statements (not just comments)"
    )


# ---------------------------------------------------------------------------
# PART 1 continued: venue_external_id writer (A, B, C)
# ---------------------------------------------------------------------------

def test_build_external_id_record_produces_10_rows():
    """Dry run over all Laos venues must produce exactly 10 external-id records,
    matching the verification artifact."""
    artifact = _load_verification_artifact()
    expected_refs = {e["ref"] for e in artifact["verified_names"]}

    records = []
    for _json_file, geo_region, venue in _iter_laos_venues():
        venue_id = "test-" + venue["name"].lower().replace(" ", "-")
        rec = build_external_id_record(venue, venue_id)
        if rec is not None:
            records.append(rec)

    assert len(records) == 10, f"Expected 10 external_id records, got {len(records)}"
    actual_refs = {r["external_id"] for r in records}
    assert actual_refs == expected_refs, (
        f"Mismatch: expected {sorted(expected_refs)}, got {sorted(actual_refs)}"
    )


def test_build_external_id_record_key_guard():
    """Payload keys from build_external_id_record must equal VENUE_EXTERNAL_ID_WRITE_COLUMNS."""
    # Find a venue that will produce a record
    for _json_file, geo_region, venue in _iter_laos_venues():
        rec = build_external_id_record(venue, "test-venue-id")
        if rec is not None:
            assert set(rec.keys()) == VENUE_EXTERNAL_ID_WRITE_COLUMNS, (
                f"Payload keys {sorted(rec.keys())} != "
                f"declared {sorted(VENUE_EXTERNAL_ID_WRITE_COLUMNS)}"
            )
            return
    pytest.fail("No venue produced an external_id record")


def test_second_run_produces_no_duplicates():
    """Running build_external_id_record twice produces identical records (idempotent).
    The UNIQUE(source, external_id) constraint means a second INSERT would use
    ON CONFLICT DO NOTHING -- same data, no error."""
    seen = {}
    for _json_file, geo_region, venue in _iter_laos_venues():
        rec = build_external_id_record(venue, "test-" + venue["name"])
        if rec is None:
            continue
        key = (rec["source"], rec["external_id"])
        if key in seen:
            pytest.fail(f"Duplicate (source, external_id): {key}")
        seen[key] = rec

    # Run again -- same venues produce same keys
    for _json_file, geo_region, venue in _iter_laos_venues():
        rec = build_external_id_record(venue, "test-" + venue["name"])
        if rec is None:
            continue
        key = (rec["source"], rec["external_id"])
        assert key in seen, f"Second run produced unknown key {key}"
        assert rec == seen[key], f"Second run produced different record for {key}"


class FakeTable:
    """Minimal fake for Supabase table fluent API."""
    def __init__(self, name, calls):
        self._name = name
        self._calls = calls

    def upsert(self, data, **kwargs):
        self._calls.append(("upsert", self._name, data, kwargs))
        return self

    def insert(self, data):
        self._calls.append(("insert", self._name, data))
        return self

    def update(self, data):
        self._calls.append(("update", self._name, data))
        return self

    def delete(self):
        self._calls.append(("delete", self._name))
        return self

    def select(self, *args):
        self._calls.append(("select", self._name, args))
        return self

    def eq(self, col, val):
        return self

    def execute(self):
        class R:
            data = []
        return R()


class FakeClient:
    """Captures calls to all tables."""
    def __init__(self):
        self.calls = []

    def table(self, name):
        return FakeTable(name, self.calls)


def test_upsert_venues_writes_external_ids(monkeypatch):
    """upsert_venues must call venue_external_id upsert for venues with refs."""
    import uuid as _uuid
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import load_venues
    sys.path.pop(0)

    # Load all Laos venues
    all_venues = []
    for _jf, geo_region, venue in _iter_laos_venues():
        all_venues.append(venue)
    geo_region = "luang_prabang_laos"  # doesn't matter, just need a valid one

    # Fake embeddings (one per venue)
    fake_embeddings = [[0.0] * 3 for _ in all_venues]

    # Patch create_client to return our fake
    fake_client = FakeClient()
    monkeypatch.setattr("os.environ", {
        "TB_SUPABASE_URL": "http://fake", "TB_SUPABASE_KEY": "fake"
    })

    # Monkey-patch the supabase import inside load_venues
    import types
    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda url, key: fake_client
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)

    # Reload to pick up the patched module
    import importlib
    importlib.reload(load_venues)

    load_venues.upsert_venues(all_venues, geo_region, fake_embeddings)

    # Check venue_external_id upserts
    ext_calls = [c for c in fake_client.calls
                 if c[0] == "upsert" and c[1] == "venue_external_id"]
    assert len(ext_calls) == 10, (
        f"Expected 10 venue_external_id upserts, got {len(ext_calls)}"
    )
    # Verify the refs match the artifact
    artifact = _load_verification_artifact()
    expected_refs = {e["ref"] for e in artifact["verified_names"]}
    actual_refs = {c[2]["external_id"] for c in ext_calls}
    assert actual_refs == expected_refs, (
        f"External ID mismatch: {sorted(actual_refs - expected_refs)}"
    )



# ---------------------------------------------------------------------------
# PART 2: taxonomy_term
# ---------------------------------------------------------------------------

def test_taxonomy_seed_completeness():
    """Every taxonomy value used in venue JSONs must exist in the migration seed."""
    seeded = _parse_taxonomy_seed_from_migration()

    missing = []
    for _json_file, _geo_region, venue in _iter_laos_venues():
        cat = venue.get("category")
        if cat and ("category", cat) not in seeded:
            missing.append(("category", cat, venue["name"]))
        for tag in venue.get("vibe_tags", []):
            if ("vibe_tag", tag) not in seeded:
                missing.append(("vibe_tag", tag, venue["name"]))
        for aud in venue.get("audience", []):
            if ("audience", aud) not in seeded:
                missing.append(("audience", aud, venue["name"]))
        pb = venue.get("price_band")
        if pb and ("price_band", pb) not in seeded:
            missing.append(("price_band", pb, venue["name"]))
        io = venue.get("indoor_outdoor")
        if io and ("indoor_outdoor", io) not in seeded:
            missing.append(("indoor_outdoor", io, venue["name"]))

    assert not missing, (
        "Taxonomy seed is incomplete -- venue data uses terms not in 0013:\n"
        + "\n".join(f"  {tax}.{term} (used by {name})" for tax, term, name in missing[:20])
    )


def test_taxonomy_seed_completeness_glossary():
    """Every dish taxonomy value in the glossary must exist in the migration seed."""
    seeded = _parse_taxonomy_seed_from_migration()
    glossary = json.loads((DATA_DIR / "laos_dish_glossary.json").read_text())

    missing = []
    for dish in glossary["dishes"]:
        name = dish.get("name_en") or dish.get("dish_key") or "?"
        for field, taxonomy in [
            ("cuisine", "cuisine"),
            ("dish_type", "dish_type"),
            ("spice_level", "spice_level"),
            ("adventurousness", "adventurousness"),
        ]:
            val = dish.get(field)
            if val is not None and (taxonomy, str(val)) not in seeded:
                missing.append((taxonomy, str(val), name))
        for val in dish.get("suitable_for", []):
            if ("suitable_for", val) not in seeded:
                missing.append(("suitable_for", val, name))
        # typical_price_band uses the price_band taxonomy
        pb = dish.get("typical_price_band")
        if pb and ("price_band", pb) not in seeded:
            missing.append(("price_band", pb, name))

    assert not missing, (
        "Taxonomy seed is incomplete -- glossary uses terms not in 0013:\n"
        + "\n".join(f"  {tax}.{term} (used by {name})" for tax, term, name in missing[:20])
    )


def test_taxonomy_seed_count():
    """The seed must contain the expected number of terms."""
    seeded = _parse_taxonomy_seed_from_migration()
    # 45 original + new dish terms
    assert len(seeded) >= 45, f"Expected at least 45 seeded terms, got {len(seeded)}"


def test_constants_match_seed_bidirectional():
    """TAXONOMY_TERMS constants and the migration seed must agree exactly.

    Enumerates ALL taxonomies dynamically from both sides, covering all 10.
    A term in the constant but not in the seed means new data validates
    locally but is rejected by the DB. A term in the seed but not the
    constant means the DB accepts data the loader would reject.
    """
    seeded = _parse_taxonomy_seed_from_migration()

    # Build set from Python constants (all taxonomies, converting to str)
    constant_pairs = set()
    for taxonomy, terms in TAXONOMY_TERMS.items():
        for term in terms:
            constant_pairs.add((taxonomy, str(term)))

    # Both sides must enumerate the same set of taxonomies
    seed_taxonomies = {t[0] for t in seeded}
    constant_taxonomies = set(TAXONOMY_TERMS.keys())
    taxonomy_diff = seed_taxonomies.symmetric_difference(constant_taxonomies)
    assert not taxonomy_diff, (
        f"Taxonomy set mismatch between seed and constants: {sorted(taxonomy_diff)}"
    )
    assert len(seed_taxonomies) == 10, (
        f"Expected 10 taxonomies, got {len(seed_taxonomies)}: {sorted(seed_taxonomies)}"
    )

    in_seed_not_constant = sorted(seeded - constant_pairs)
    in_constant_not_seed = sorted(constant_pairs - seeded)

    problems = []
    if in_seed_not_constant:
        problems.append(
            "In migration seed but NOT in TAXONOMY_TERMS constant "
            "(DB accepts data the loader would reject):\n"
            + "\n".join(f"  {t[0]}.{t[1]}" for t in in_seed_not_constant)
        )
    if in_constant_not_seed:
        problems.append(
            "In TAXONOMY_TERMS constant but NOT in migration seed "
            "(validates locally but rejected by DB):\n"
            + "\n".join(f"  {t[0]}.{t[1]}" for t in in_constant_not_seed)
        )
    assert not problems, "\n\n".join(problems)


def test_taxonomy_composite_pk():
    """The migration must use a composite PRIMARY KEY (taxonomy, term) in SQL."""
    migration = MIGRATIONS_DIR / "0013_taxonomy_term.sql"
    sql = _strip_sql_comments(migration.read_text(encoding="utf-8"))
    assert re.search(r"PRIMARY\s+KEY\s*\(\s*taxonomy\s*,\s*term\s*\)", sql), (
        "Migration 0013 must have PRIMARY KEY (taxonomy, term) in SQL statements"
    )


# ---------------------------------------------------------------------------
# Migration safety: additive-only
# ---------------------------------------------------------------------------

def test_migration_0012_is_additive_only():
    """Migration 0012 must not DROP anything or ALTER venues_rag."""
    migration = MIGRATIONS_DIR / "0012_venue_external_id.sql"
    sql = _strip_sql_comments(migration.read_text(encoding="utf-8"))
    assert not re.search(r"\bDROP\b", sql, re.IGNORECASE), (
        "Migration 0012 contains a DROP statement"
    )
    assert not re.search(r"ALTER\s+TABLE\s+venues_rag", sql, re.IGNORECASE), (
        "Migration 0012 alters the existing venues_rag table"
    )


def test_migration_0013_is_additive_only():
    """Migration 0013 must not DROP anything or ALTER venues_rag."""
    migration = MIGRATIONS_DIR / "0013_taxonomy_term.sql"
    sql = _strip_sql_comments(migration.read_text(encoding="utf-8"))
    assert not re.search(r"\bDROP\b", sql, re.IGNORECASE), (
        "Migration 0013 contains a DROP statement"
    )
    assert not re.search(r"ALTER\s+TABLE\s+venues_rag", sql, re.IGNORECASE), (
        "Migration 0013 alters the existing venues_rag table"
    )
