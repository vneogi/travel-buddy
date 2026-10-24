"""SPEC-43 Gap 2: PostgREST isolation via RLS and grants (migration 0026).

Static text checks only. No live Postgres. Hosted two-JWT proof is owner
SQL after merge.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
MIGRATION_0026 = MIGRATIONS_DIR / "0026_spec43_g2_rls.sql"

PERSONAL_TABLES = (
    "user_tiers",
    "trip_states",
    "event_log",
    "cached_responses",
    "trip_node",
    "trip_edge",
    "trip_command",
    "trip_party",
    "party_member",
    "signal",
)

CATALOG_TABLES = (
    "venues_rag",
    "venue_dish",
    "signal_type",
    "source",
    "taxonomy_term",
    "dish_glossary",
    "venue_external_id",
)

TRIP_SCOPED_TABLES = ("trip_node", "trip_edge", "trip_command", "trip_party", "party_member")


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_0026.is_file(), "0026_spec43_g2_rls.sql must exist"
    return _norm(_strip_sql_comments(MIGRATION_0026.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def _policies(statements: list[str]) -> list[tuple[str, str, str]]:
    """Return (policy_name, table, full_statement) for each CREATE POLICY."""
    out = []
    for stmt in statements:
        m = re.match(r"create policy (\w+) on (\w+)\b", stmt)
        if m:
            out.append((m.group(1), m.group(2), stmt))
    return out


def test_trip_states_force_rls_is_present_in_0026(sql: str) -> None:
    assert "alter table trip_states force row level security" in sql


@pytest.mark.parametrize("table", PERSONAL_TABLES)
def test_personal_table_enables_and_forces_rls(sql: str, table: str) -> None:
    assert f"alter table {table} enable row level security" in sql
    assert f"alter table {table} force row level security" in sql


@pytest.mark.parametrize("table", PERSONAL_TABLES)
def test_personal_table_revokes_anon_and_authenticated(statements: list[str], table: str) -> None:
    revokes = [s for s in statements if re.match(rf"revoke all on table {table} from ", s)]
    assert revokes, f"no REVOKE ALL for {table}"
    grantees = revokes[0].split(" from ", 1)[1]
    for role in ("public", "anon", "authenticated"):
        assert role in [g.strip() for g in grantees.split(",")], f"{table} not revoked from {role}"


@pytest.mark.parametrize("table", PERSONAL_TABLES)
def test_personal_table_grants_service_role(sql: str, table: str) -> None:
    assert f"grant all on table {table} to service_role" in sql


@pytest.mark.parametrize("table", PERSONAL_TABLES)
def test_personal_table_never_granted_to_anon_or_authenticated(
    statements: list[str], table: str
) -> None:
    for stmt in statements:
        m = re.match(rf"grant .+ on table {table} to (.+)$", stmt)
        if m:
            grantees = {g.strip() for g in m.group(1).split(",")}
            assert not grantees & {"anon", "authenticated", "public"}, stmt


def test_no_with_check_true_on_party_tables(statements: list[str]) -> None:
    for _name, table, stmt in _policies(statements):
        if table in ("trip_party", "party_member"):
            assert not re.search(r"with check \(\s*true\s*\)", stmt), stmt


def test_no_with_check_true_anywhere_in_0026(sql: str) -> None:
    assert not re.search(r"with check \(\s*true\s*\)", sql)


def test_0007_party_insert_policies_are_dropped_and_replaced(sql: str, statements) -> None:
    for name, table in (
        ("trip_party_insert_own", "trip_party"),
        ("party_member_insert_own", "party_member"),
        ("trip_party_select_own", "trip_party"),
        ("party_member_select_own", "party_member"),
    ):
        assert f"drop policy if exists {name} on {table}" in sql
        recreated = [s for n, t, s in _policies(statements) if n == name and t == table]
        assert len(recreated) == 1, name
        assert "trip_states" in recreated[0] and "auth.uid()" in recreated[0]


@pytest.mark.parametrize("table", TRIP_SCOPED_TABLES)
def test_trip_scoped_policies_own_via_trip_states(statements: list[str], table: str) -> None:
    policies = [s for _n, t, s in _policies(statements) if t == table]
    assert policies, f"no owner policy on {table}"
    for stmt in policies:
        assert "trip_states" in stmt and "auth.uid()" in stmt, stmt
        assert "from signal" not in stmt, f"{table} must not use signal as ownership"


def test_owner_policies_are_authenticated_only_and_keyed_on_auth_uid(statements) -> None:
    for name, table, stmt in _policies(statements):
        if table in PERSONAL_TABLES:
            assert re.search(r"\bto authenticated\b", stmt), name
            assert " anon" not in stmt.split(" using ", 1)[0].split(" with check ", 1)[0], name
            assert "auth.uid()" in stmt, name
            assert "using (true)" not in stmt, name


def test_cached_responses_has_no_authenticated_policy(statements) -> None:
    # No owner column exists; service_role only.
    assert not [n for n, t, _s in _policies(statements) if t == "cached_responses"]


@pytest.mark.parametrize("table", CATALOG_TABLES)
def test_catalog_tables_are_select_only_for_public_roles(statements, sql: str, table: str) -> None:
    assert f"alter table {table} enable row level security" in sql
    assert f"grant select on table {table} to anon, authenticated" in sql
    for stmt in statements:
        m = re.match(rf"grant (.+) on table {table} to (.+)$", stmt)
        if not m:
            continue
        privileges = {p.strip() for p in m.group(1).split(",")}
        grantees = {g.strip() for g in m.group(2).split(",")}
        if grantees & {"anon", "authenticated", "public"}:
            assert privileges == {"select"}, stmt


@pytest.mark.parametrize("table", CATALOG_TABLES)
def test_catalog_tables_not_granted_insert_to_anon(statements, table: str) -> None:
    for stmt in statements:
        m = re.match(rf"grant (.+) on table {table} to (.+)$", stmt)
        if m and "anon" in {g.strip() for g in m.group(2).split(",")}:
            assert "insert" not in m.group(1) and "all" not in m.group(1), stmt


def test_every_migration_table_is_classified() -> None:
    created: set[str] = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        text = _strip_sql_comments(path.read_text(encoding="utf-8"))
        created |= {
            m.lower()
            for m in re.findall(
                r"create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)", text, flags=re.IGNORECASE
            )
        }
    unclassified = created - set(PERSONAL_TABLES) - set(CATALOG_TABLES)
    assert not unclassified, f"tables not covered by 0026: {sorted(unclassified)}"


def test_0007_not_edited_in_place() -> None:
    text = (MIGRATIONS_DIR / "0007_enable_rls.sql").read_text(encoding="utf-8")
    assert "trip_party_insert_own" in text and "WITH CHECK (true)" in text


def test_0026_is_ascii_only() -> None:
    MIGRATION_0026.read_text(encoding="utf-8").encode("ascii")


def test_service_role_not_referenced_in_flutter() -> None:
    lib = REPO_ROOT / "mobile" / "lib"
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in lib.rglob("*.dart")
        if re.search(r"service_role|SERVICE_ROLE", p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders
