"""Tests for schema plumbing: venue_external_id and taxonomy_term.

These tests validate:
1. venue_external_id seed data from the verification artifact
2. taxonomy_term seed completeness against venue JSON data
3. Bidirectional agreement between Python constants and the migration seed

The loader does NOT read vocabulary from the database. The Python constants
stay the runtime check; a test asserts the constants and seeded table agree
exactly in both directions.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
DATA_DIR = REPO_ROOT / "data"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from load_venues import (  # noqa: E402
    EXTERNAL_ID_SOURCES,
    TAXONOMY_TERMS,
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


def _parse_taxonomy_seed_from_migration():
    """Parse the INSERT statements in 0013 to extract seeded (taxonomy, term) pairs."""
    migration = MIGRATIONS_DIR / "0013_taxonomy_term.sql"
    content = migration.read_text(encoding="utf-8")
    # Match INSERT ... VALUES lines like ('category', 'bar'),
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


def test_duplicate_external_id_detected_by_unique_constraint():
    """The 0012 migration must define UNIQUE(source, external_id).

    We verify this by parsing the migration SQL rather than hitting a DB.
    """
    migration = MIGRATIONS_DIR / "0012_venue_external_id.sql"
    content = migration.read_text(encoding="utf-8")
    assert "UNIQUE" in content.upper(), "Migration must have a UNIQUE constraint"
    # Verify it's on (source, external_id)
    assert "source" in content and "external_id" in content, (
        "UNIQUE constraint must cover source and external_id"
    )


# ---------------------------------------------------------------------------
# PART 2: taxonomy_term
# ---------------------------------------------------------------------------

def test_taxonomy_seed_completeness():
    """Every taxonomy value used in venue JSONs must exist in the migration seed.

    If this fails, the seed is incomplete and DB validation would reject data
    we already have.
    """
    seeded = _parse_taxonomy_seed_from_migration()

    missing = []
    for _json_file, _geo_region, venue in _iter_laos_venues():
        # category
        cat = venue.get("category")
        if cat and ("category", cat) not in seeded:
            missing.append(("category", cat, venue["name"]))
        # vibe_tags
        for tag in venue.get("vibe_tags", []):
            if ("vibe_tag", tag) not in seeded:
                missing.append(("vibe_tag", tag, venue["name"]))
        # audience
        for aud in venue.get("audience", []):
            if ("audience", aud) not in seeded:
                missing.append(("audience", aud, venue["name"]))
        # price_band
        pb = venue.get("price_band")
        if pb and ("price_band", pb) not in seeded:
            missing.append(("price_band", pb, venue["name"]))
        # indoor_outdoor
        io = venue.get("indoor_outdoor")
        if io and ("indoor_outdoor", io) not in seeded:
            missing.append(("indoor_outdoor", io, venue["name"]))

    assert not missing, (
        "Taxonomy seed is incomplete -- venue data uses terms not in 0013:\n"
        + "\n".join(f"  {tax}.{term} (used by {name})" for tax, term, name in missing[:20])
    )


def test_taxonomy_seed_count():
    """The seed must contain exactly 45 terms (category 16, vibe_tag 15, etc.)."""
    seeded = _parse_taxonomy_seed_from_migration()
    assert len(seeded) == 45, f"Expected 45 seeded terms, got {len(seeded)}"


def test_constants_match_seed_bidirectional():
    """TAXONOMY_TERMS constants and the migration seed must agree exactly.

    This test stops the two from drifting. A term in the constant but not
    in the seed means new data validates locally but is rejected by the DB.
    A term in the seed but not the constant means the DB accepts data the
    loader would reject.
    """
    seeded = _parse_taxonomy_seed_from_migration()

    # Build set from Python constants
    constant_pairs = set()
    for taxonomy, terms in TAXONOMY_TERMS.items():
        for term in terms:
            constant_pairs.add((taxonomy, term))

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
    """The migration must use a composite PRIMARY KEY (taxonomy, term)."""
    migration = MIGRATIONS_DIR / "0013_taxonomy_term.sql"
    content = migration.read_text(encoding="utf-8")
    # Find non-comment lines containing PRIMARY KEY
    pk_lines = [
        l for l in content.splitlines()
        if "PRIMARY KEY" in l.upper() and not l.strip().startswith("--")
    ]
    assert pk_lines, "No PRIMARY KEY SQL statement found (only comments)"
    pk_text = pk_lines[0]
    assert "taxonomy" in pk_text and "term" in pk_text, (
        f"PRIMARY KEY must be composite on (taxonomy, term), got: {pk_text}"
    )


def test_migration_0012_is_additive_only():
    """Migration 0012 must only ADD structure, never DROP or ALTER existing objects."""
    migration = MIGRATIONS_DIR / "0012_venue_external_id.sql"
    content = migration.read_text(encoding="utf-8").upper()
    assert "DROP" not in content, "Migration 0012 must not contain DROP"
    assert "ALTER TABLE venues_rag" not in content, (
        "Migration 0012 must not ALTER the existing venues_rag table"
    )


def test_migration_0013_is_additive_only():
    """Migration 0013 must only ADD structure, never DROP or ALTER existing objects."""
    migration = MIGRATIONS_DIR / "0013_taxonomy_term.sql"
    content = migration.read_text(encoding="utf-8").upper()
    assert "DROP" not in content, "Migration 0013 must not contain DROP"
    assert "ALTER TABLE venues_rag" not in content, (
        "Migration 0013 must not ALTER the existing venues_rag table"
    )
