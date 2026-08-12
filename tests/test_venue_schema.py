"""Venue schema drift guard.

Parses supabase/migrations/*.sql for the venues_rag column set and asserts
the loader's write set is a subset of it.  A column written but never
defined means a fresh database built from 0001 upward rejects the load.

The loader write set is declared as an explicit constant here because
load_venues.py is being rewritten in G3.  A second assertion verifies
every name in that constant literally appears in scripts/load_venues.py,
so a G3 rename cannot leave a stale mirror behind -- it fails instead.

# G3 replaces LOADER_WRITES_TO_VENUES_RAG with an import from the loader.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
LOADER_PATH = REPO_ROOT / "scripts" / "load_venues.py"

# Measured Aug 13 2026 from the insert dict at lines 371-389.
# G3 replaces this constant with an import from the loader module.
LOADER_WRITES_TO_VENUES_RAG = frozenset({
    "audience",
    "bid_weight",
    "category",
    "description",
    "embedding",
    "geo_region",
    "indoor_outdoor",
    "is_sponsored",
    "lat",
    "lng",
    "micro_location",
    "name",
    "opening_hours_structured",
    "price_band",
    "typical_dwell_minutes",
    "venue_id",
    "vibe_tags",
})


def _parse_venues_rag_columns():
    """Extract the set of column names defined for venues_rag across all migrations."""
    columns = set()

    # Pattern for CREATE TABLE columns (indented lines between CREATE TABLE and );)
    create_re = re.compile(
        r"CREATE TABLE IF NOT EXISTS venues_rag\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )
    # Pattern for ALTER TABLE ... ADD COLUMN
    alter_re = re.compile(
        r"ALTER TABLE venues_rag\s+ADD COLUMN IF NOT EXISTS\s+(\w+)",
        re.IGNORECASE,
    )
    # Column definition line inside CREATE TABLE (skip constraints, indexes)
    col_line_re = re.compile(r"^\s+(\w+)\s+(?:UUID|TEXT|INTEGER|BOOLEAN|FLOAT|DOUBLE|NUMERIC|VECTOR|TIMESTAMP|JSONB|TIMESTAMPTZ)", re.IGNORECASE)

    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        content = sql_file.read_text(encoding="utf-8")

        # CREATE TABLE
        for m in create_re.finditer(content):
            body = m.group(1)
            for line in body.split("\n"):
                col_m = col_line_re.match(line)
                if col_m:
                    columns.add(col_m.group(1))

        # ALTER TABLE ADD COLUMN
        for m in alter_re.finditer(content):
            columns.add(m.group(1))

    return columns


def test_loader_writes_subset_of_migrations():
    """Every column the loader writes must be defined by a migration."""
    defined = _parse_venues_rag_columns()
    undefined = sorted(LOADER_WRITES_TO_VENUES_RAG - defined)
    assert not undefined, (
        "Loader writes columns with no migration definition -- a fresh DB "
        "built from 0001 upward will reject the load:\n"
        + "\n".join("  " + c for c in undefined)
    )


def test_loader_constant_matches_source():
    """Every name in the constant must literally appear in load_venues.py.

    This prevents the constant from going stale after a G3 rename.
    """
    source = LOADER_PATH.read_text(encoding="utf-8")
    missing = sorted(
        col for col in LOADER_WRITES_TO_VENUES_RAG
        if ('"' + col + '"') not in source
    )
    assert not missing, (
        "Columns in LOADER_WRITES_TO_VENUES_RAG not found (quoted) in "
        "scripts/load_venues.py -- stale after rename?\n"
        + "\n".join("  " + c for c in missing)
    )
