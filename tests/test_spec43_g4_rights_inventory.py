"""SPEC-43 Gap 4 slice 1: every migration table has a data-rights entry, and a
new identity-bearing table fails this guard until it is classified.

Reads supabase/migrations/*.sql only. No database, no network.
"""

import re
import shutil
from pathlib import Path

import pytest

from config.data_rights import (
    IDENTITY_COLUMNS,
    IDENTITY_VALUES,
    RETENTION_VALUES,
    RIGHTS_KEYS,
    RIGHTS_MAP,
    identity_tables,
    stale,
    strip_sql_comments,
    unclassified,
    walk_created_tables,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


@pytest.fixture(scope="module")
def created():
    return walk_created_tables(MIGRATIONS_DIR)


def test_walker_finds_real_tables(created):
    assert created, "no tables found; walker or path is broken"
    # Comment-only DROP TABLE lines in 0001 must not remove trip_states.
    assert "trip_states" in created
    assert "trip_node" in created


def test_every_migration_table_has_rights_classification(created):
    missing = unclassified(created, RIGHTS_MAP)
    assert not missing, f"tables without a RIGHTS_MAP entry: {sorted(missing)}"


def test_no_stale_rights_entries(created):
    extra = stale(created, RIGHTS_MAP)
    assert not extra, f"RIGHTS_MAP entries for tables no migration creates: {sorted(extra)}"


def test_identity_tables_are_not_classified_none():
    found = identity_tables(MIGRATIONS_DIR)
    assert found, "no identity tables found; detection is broken"
    for table in sorted(found):
        assert RIGHTS_MAP[table]["identity"] != "none", table


def test_identity_tables_match_column_scan():
    # Independent check: plain text scan of each table's columns.
    pattern = re.compile(r"\b(" + "|".join(IDENTITY_COLUMNS) + r")\b", re.IGNORECASE)
    expected = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        text = strip_sql_comments(path.read_text(encoding="utf-8"))
        for chunk in re.split(r"(?i)\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?", text)[1:]:
            name = re.match(r"(\w+)", chunk).group(1).lower()
            if pattern.search(chunk.split(";", 1)[0]):
                expected.add(name)
    assert identity_tables(MIGRATIONS_DIR) == expected


def test_slice_one_only_plans_export_and_delete():
    for table, entry in RIGHTS_MAP.items():
        assert set(entry) == RIGHTS_KEYS, table
        assert entry["identity"] in IDENTITY_VALUES, table
        assert entry["export"] == "planned", table
        assert entry["delete"] == "planned", table
        assert entry["retention"] in RETENTION_VALUES, table
        note = entry["note"]
        assert note and note.isascii() and "\n" not in note, table


def test_personal_tables_plan_retention():
    for table, entry in RIGHTS_MAP.items():
        if entry["identity"] != "none":
            assert entry["retention"] == "planned", table


def test_synthetic_identity_table_is_unclassified(tmp_path):
    for path in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(path, tmp_path / path.name)
    (tmp_path / "9999_synthetic_identity.sql").write_text(
        "CREATE TABLE synthetic_identity (id uuid primary key, user_id uuid not null);\n",
        encoding="utf-8",
    )
    assert "synthetic_identity" in unclassified(walk_created_tables(tmp_path), RIGHTS_MAP)
    assert "synthetic_identity" in identity_tables(tmp_path)
    assert "synthetic_identity" not in RIGHTS_MAP


def test_walker_respects_drop_table(tmp_path):
    (tmp_path / "0001_create.sql").write_text(
        "create table if not exists scratch_table (id int, owner_id uuid);\n"
        "create table keeper (id int);\n",
        encoding="utf-8",
    )
    (tmp_path / "0002_drop.sql").write_text(
        "-- DROP TABLE keeper;\n/* DROP TABLE keeper; */\nDROP TABLE IF EXISTS scratch_table;\n",
        encoding="utf-8",
    )
    tables = walk_created_tables(tmp_path)
    assert "scratch_table" not in tables
    assert "scratch_table" not in identity_tables(tmp_path)
    assert "keeper" in tables


def test_comment_markers_inside_strings_are_kept(tmp_path):
    (tmp_path / "0001.sql").write_text(
        "create table a (id int, note text default '-- not a comment');\n"
        "create table b (id int, user_id uuid);\n",
        encoding="utf-8",
    )
    assert walk_created_tables(tmp_path) == {"a", "b"}
    assert identity_tables(tmp_path) == {"b"}
