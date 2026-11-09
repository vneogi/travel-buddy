"""SPEC-43 Gap 4 slice 10: export plan covers every identity table. Pure data."""

import ast
from pathlib import Path

import pytest

from config.data_rights import RIGHTS_MAP
from services import data_rights_export as export_module
from services.data_rights_erase import ERASE_REQUIRED
from services.data_rights_export import (
    EXPORT_METHODS,
    EXPORT_REQUIRED,
    EXPORT_STEPS,
    METHOD_FOR_IDENTITY,
    STEP_KEYS,
    extra_export_steps,
    missing_export_steps,
    plan_export,
)

TRIP_CHILDREN = ("trip_node", "trip_edge", "trip_party", "party_member")


def _order():
    return [s["table"] for s in EXPORT_STEPS]


def test_export_required_matches_erase_required():
    assert EXPORT_REQUIRED == ERASE_REQUIRED
    assert set(_order()) == set(ERASE_REQUIRED)
    assert EXPORT_REQUIRED == frozenset(t for t, e in RIGHTS_MAP.items() if e["identity"] != "none")


def test_every_identity_table_has_an_export_step():
    assert missing_export_steps() == set()
    assert EXPORT_REQUIRED <= set(_order())


def test_no_export_steps_for_none_identity_tables():
    assert extra_export_steps() == set()
    none_tables = {t for t, e in RIGHTS_MAP.items() if e["identity"] == "none"}
    assert "cached_responses" in none_tables
    assert {"venues_rag", "venue_dish", "dish_glossary"} <= none_tables
    assert not none_tables & set(_order())


def test_each_table_has_exactly_one_export_step():
    order = _order()
    assert len(order) == len(set(order))
    for step in EXPORT_STEPS:
        assert set(step) == STEP_KEYS
        assert isinstance(step["note"], str) and step["note"].strip()
        assert step["note"].isascii() and "\n" not in step["note"]


def test_export_step_method_matches_rights_identity():
    assert EXPORT_METHODS == {"fetch_where_user_id", "fetch_via_trip_states", "fetch_via_party"}
    for step in EXPORT_STEPS:
        method, via = METHOD_FOR_IDENTITY[RIGHTS_MAP[step["table"]]["identity"]]
        assert (step["method"], step["via"]) == (method, via), step["table"]
        assert step["method"] in EXPORT_METHODS
        assert step["method"].startswith("fetch_")


def test_export_order_is_parents_before_children():
    order = _order()
    assert order[:2] == ["user_tiers", "trip_states"]
    for child in TRIP_CHILDREN:
        assert order.index("user_tiers") < order.index(child), child
        assert order.index("trip_states") < order.index(child), child
    assert order.index("trip_party") < order.index("party_member")
    # Every via_trip_states / via_party table comes after trip_states.
    for table in order:
        if RIGHTS_MAP[table]["identity"] in ("via_trip_states", "via_party"):
            assert order.index("trip_states") < order.index(table), table


def test_plan_export_includes_user_id_on_every_step():
    plan = plan_export("user-g4-export-1")
    assert [s["table"] for s in plan] == _order()
    for step in plan:
        assert step["user_id"] == "user-g4-export-1"
        assert set(step) == STEP_KEYS | {"user_id"}
    plan[0]["table"] = "mutated"
    plan[0]["note"] = "mutated"
    assert EXPORT_STEPS[0]["table"] == "user_tiers"
    assert all("user_id" not in s for s in EXPORT_STEPS)


@pytest.mark.parametrize("bad", [None, "", "   ", 42, b"user"])
def test_plan_export_rejects_blank_user_id(bad):
    with pytest.raises(ValueError):
        plan_export(bad)


def test_synthetic_identity_table_without_export_step_is_detected():
    rights = dict(RIGHTS_MAP)
    rights["synthetic_identity"] = {
        "identity": "direct_user_id",
        "export": "planned",
        "delete": "planned",
        "retention": "planned",
        "note": "Synthetic table for the guard.",
    }
    assert "synthetic_identity" in missing_export_steps(rights=rights, steps=EXPORT_STEPS)
    assert "synthetic_identity" not in RIGHTS_MAP
    assert "synthetic_identity" not in _order()
    extra = list(EXPORT_STEPS) + [dict(EXPORT_STEPS[0], table="cached_responses")]
    assert extra_export_steps(steps=extra) == {"cached_responses"}


def test_export_module_has_no_supabase_import():
    source = Path(export_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= {"__future__", "typing", "config"}, roots
    assert not roots & {"supabase", "litellm", "httpx", "psycopg", "psycopg2", "logging"}
    assert "print(" not in source
    assert not hasattr(export_module, "execute_export")
