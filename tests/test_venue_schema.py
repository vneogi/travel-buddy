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
from load_venues import INTENTIONALLY_NOT_PERSISTED, VENUES_RAG_WRITE_COLUMNS  # noqa: E402

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


def test_no_silent_key_drop():
    """Every key present in any venue record must be accounted for.

    A key is accounted for if it appears in VENUES_RAG_WRITE_COLUMNS
    (written to the database) or in INTENTIONALLY_NOT_PERSISTED (with a
    reason comment).  A key in neither set means the loader is silently
    discarding curated data.
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
    accounted_for = VENUES_RAG_WRITE_COLUMNS | INTENTIONALLY_NOT_PERSISTED | synthetic_keys

    dropped = sorted(all_keys - accounted_for)
    assert not dropped, (
        "Venue JSON keys silently discarded by the loader -- add to "
        "VENUES_RAG_WRITE_COLUMNS (and the insert dict) or to "
        "INTENTIONALLY_NOT_PERSISTED with a reason:\n"
        + "\n".join("  " + k for k in dropped)
    )
