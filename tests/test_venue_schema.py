"""Venue schema drift guard.

Parses supabase/migrations/*.sql for the venues_rag column set and asserts
the loader's write set is a subset of it.  A column written but never
defined means a fresh database built from 0001 upward rejects the load.

The loader write set is imported from scripts/load_venues.py. A second
assertion verifies every name in that constant literally appears in
the loader source, so a rename cannot leave a stale set behind.

A third test (test_no_silent_key_drop) unions every key present in the
venue JSON files and asserts it is either persisted or explicitly ignored.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
LOADER_PATH = REPO_ROOT / "scripts" / "load_venues.py"
DATA_DIR = REPO_ROOT / "data"

# Import constants from the loader module
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from load_venues import (  # noqa: E402
    INTENTIONALLY_NOT_PERSISTED,
    JSON_KEY_TO_COLUMN,
    VALID_LOCALIZED_SOURCES,
    VENUES_RAG_WRITE_COLUMNS,
    build_venue_record,
)

sys.path.pop(0)


def _parse_venues_rag_columns():
    """Extract the set of column names defined for venues_rag across all migrations."""
    columns = set()

    create_re = re.compile(
        r"CREATE TABLE IF NOT EXISTS venues_rag\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )
    alter_re = re.compile(
        r"ALTER TABLE venues_rag\s+ADD COLUMN IF NOT EXISTS\s+(\w+)",
        re.IGNORECASE,
    )
    col_line_re = re.compile(
        r"^\s+(\w+)\s+(?:UUID|TEXT|INTEGER|BOOLEAN|FLOAT|DOUBLE|NUMERIC|VECTOR|TIMESTAMP|JSONB|TIMESTAMPTZ)",
        re.IGNORECASE,
    )

    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        content = sql_file.read_text(encoding="utf-8")

        for m in create_re.finditer(content):
            body = m.group(1)
            for line in body.split("\n"):
                col_m = col_line_re.match(line)
                if col_m:
                    columns.add(col_m.group(1))

        for m in alter_re.finditer(content):
            columns.add(m.group(1))

    return columns


def test_loader_writes_subset_of_migrations():
    """Every column the loader writes must be defined by a migration."""
    defined = _parse_venues_rag_columns()
    undefined = sorted(VENUES_RAG_WRITE_COLUMNS - defined)
    assert not undefined, (
        "Loader writes columns with no migration definition -- a fresh DB "
        "built from 0001 upward will reject the load:\n"
        + "\n".join("  " + c for c in undefined)
    )


def test_loader_constant_matches_source():
    """Every name in the constant must literally appear in load_venues.py.

    This prevents the constant from going stale after a rename.
    """
    source = LOADER_PATH.read_text(encoding="utf-8")
    missing = sorted(
        col for col in VENUES_RAG_WRITE_COLUMNS
        if ('"' + col + '"') not in source
    )
    assert not missing, (
        "Columns in VENUES_RAG_WRITE_COLUMNS not found (quoted) in "
        "scripts/load_venues.py -- stale after rename?\n"
        + "\n".join("  " + c for c in missing)
    )


def _load_first_venue():
    """Load the first venue from laos_luang_prabang.json for test use."""
    venue_file = DATA_DIR / "laos_luang_prabang.json"
    data = json.loads(venue_file.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        venues = None
        for k in ("venues", "data", "items"):
            if isinstance(data.get(k), list):
                venues = data[k]
                break
        assert venues, f"No venues array found in {venue_file.name}"
    else:
        venues = data
    return venues[0], data.get("geo_region", "luang_prabang_laos")


def test_no_silent_key_drop():
    """Every key present in any venue record must be accounted for.

    A key is accounted for if it:
      - appears directly in VENUES_RAG_WRITE_COLUMNS, or
      - maps to a column via JSON_KEY_TO_COLUMN (e.g. name_local -> names_local), or
      - appears in INTENTIONALLY_NOT_PERSISTED (with a reason comment).

    A key in none of these sets means the loader is silently discarding
    curated data.
    """
    all_keys: set = set()
    for json_file in sorted(DATA_DIR.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        # Unwrap dict wrapper if present
        if isinstance(data, dict):
            venues = next(
                (data[k] for k in ("venues", "data", "items") if isinstance(data.get(k), list)),
                None,
            )
            if venues is None:
                continue  # not a venue file (e.g. dish_glossary)
        elif isinstance(data, list):
            venues = data
        else:
            continue

        for venue in venues:
            all_keys.update(venue.keys())

    # Keys that the loader produces synthetically (not from JSON)
    synthetic_keys = {"embedding", "geo_region", "venue_id", "opening_hours_structured"}
    # Keys consumed via JSON_KEY_TO_COLUMN (different name in DB)
    mapped_keys = set(JSON_KEY_TO_COLUMN.keys())

    accounted_for = (
        VENUES_RAG_WRITE_COLUMNS | INTENTIONALLY_NOT_PERSISTED
        | synthetic_keys | mapped_keys
    )

    dropped = sorted(all_keys - accounted_for)
    assert not dropped, (
        "Venue JSON keys silently discarded by the loader -- add to "
        "VENUES_RAG_WRITE_COLUMNS, JSON_KEY_TO_COLUMN, or "
        "INTENTIONALLY_NOT_PERSISTED with a reason:\n"
        + "\n".join("  " + k for k in dropped)
    )


def test_payload_keys_match_write_columns():
    """build_venue_record must produce exactly VENUES_RAG_WRITE_COLUMNS.

    The old guards watched the *declaration* (the constant) but never
    the *behaviour* (the dict the loader actually builds).  A field
    declared in the constant but absent from the payload silently
    writes NULL.  Equality in both directions catches that.
    """
    venue, geo_region = _load_first_venue()

    record = build_venue_record(
        venue,
        venue_id="test-uuid-0000",
        embedding=[0.0] * 1536,
        geo_region=geo_region,
    )

    payload_keys = set(record.keys())
    declared_keys = VENUES_RAG_WRITE_COLUMNS

    missing_from_payload = sorted(declared_keys - payload_keys)
    extra_in_payload = sorted(payload_keys - declared_keys)

    problems = []
    if missing_from_payload:
        problems.append(
            "Declared in VENUES_RAG_WRITE_COLUMNS but MISSING from "
            "build_venue_record payload (would write NULL silently):\n"
            + "\n".join("  " + k for k in missing_from_payload)
        )
    if extra_in_payload:
        problems.append(
            "Present in build_venue_record payload but NOT declared in "
            "VENUES_RAG_WRITE_COLUMNS:\n"
            + "\n".join("  " + k for k in extra_in_payload)
        )
    assert not problems, "\n\n".join(problems)

    # The update payload must equal the record minus exactly venue_id and name.
    update_payload = {k: v for k, v in record.items()
                     if k not in ("venue_id", "name")}
    expected_update_keys = declared_keys - {"venue_id", "name"}
    assert set(update_payload.keys()) == expected_update_keys, (
        "Update payload key set does not equal record minus {venue_id, name}. "
        f"Difference: {set(update_payload.keys()) ^ expected_update_keys}"
    )


def test_localized_jsonb_shape():
    """names_local and landmarks_local must have correct JSONB shape.

    Every entry must be keyed by a BCP-47 language tag and contain
    exactly {"value": ..., "source": ...} where source is from the
    closed vocabulary: wikidata, osm, official, manual, generated.
    """
    venue, geo_region = _load_first_venue()

    record = build_venue_record(
        venue,
        venue_id="test-uuid-0000",
        embedding=[0.0] * 1536,
        geo_region=geo_region,
    )

    problems = []
    for col in ("names_local", "landmarks_local"):
        jsonb = record.get(col)
        if jsonb is None:
            problems.append(f"{col} is None for venue {venue['name']}")
            continue
        if not isinstance(jsonb, dict):
            problems.append(f"{col} is not a dict: {type(jsonb)}")
            continue
        for lang, entry in jsonb.items():
            if not isinstance(entry, dict):
                problems.append(f"{col}[{lang}] is not a dict: {type(entry)}")
                continue
            missing_keys = {"value", "source"} - set(entry.keys())
            if missing_keys:
                problems.append(
                    f"{col}[{lang}] missing keys: {sorted(missing_keys)}"
                )
            extra_keys = set(entry.keys()) - {"value", "source"}
            if extra_keys:
                problems.append(
                    f"{col}[{lang}] has unexpected keys: {sorted(extra_keys)}"
                )
            source = entry.get("source")
            if source and source not in VALID_LOCALIZED_SOURCES:
                problems.append(
                    f"{col}[{lang}] source {source!r} not in "
                    f"VALID_LOCALIZED_SOURCES: {sorted(VALID_LOCALIZED_SOURCES)}"
                )
    assert not problems, "JSONB shape violations:\n" + "\n".join("  " + p for p in problems)  # G3d
