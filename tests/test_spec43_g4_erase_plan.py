"""SPEC-43 Gap 4 slice 2: the erase plan covers every identity table, in order.

Pure data checks. No database, no network.
"""

import ast
from pathlib import Path

import pytest

from config.data_rights import RIGHTS_MAP
from services import data_rights_erase as erase_module
from services.data_rights_erase import (
    ERASE_METHODS,
    ERASE_REQUIRED,
    ERASE_STEPS,
    STEP_KEYS,
    extra_erase_steps,
    missing_erase_steps,
    plan_erase,
)

# Independent of the module's own mapping.
EXPECTED_METHOD = {
    "direct_user_id": ("delete_where_user_id", None),
    "via_trip_states": ("delete_via_trip_states", "trip_states.trip_id"),
    "via_party": ("delete_via_party", "trip_party.party_id->trip_states"),
}
USER_ID = "user-g4-erase-3d9c"


def _order():
    return [s["table"] for s in ERASE_STEPS]


def test_erase_required_is_derived_from_rights_map():
    expected = {t for t, e in RIGHTS_MAP.items() if e["identity"] != "none"}
    assert ERASE_REQUIRED == frozenset(expected)
    assert "trip_states" in ERASE_REQUIRED


def test_every_identity_table_has_an_erase_step():
    missing = missing_erase_steps()
    assert not missing, f"identity tables without an erase step: {sorted(missing)}"


def test_no_erase_steps_for_none_identity_tables():
    assert not extra_erase_steps()
    assert "cached_responses" not in _order()
    for table in _order():
        assert RIGHTS_MAP[table]["identity"] != "none", table


def test_each_table_has_exactly_one_step():
    order = _order()
    assert len(order) == len(set(order))
    assert order.count("user_tiers") == 1


def test_erase_step_method_matches_rights_identity():
    for step in ERASE_STEPS:
        assert set(step) == STEP_KEYS, step["table"]
        assert step["method"] in ERASE_METHODS, step["table"]
        method, via = EXPECTED_METHOD[RIGHTS_MAP[step["table"]]["identity"]]
        assert step["method"] == method, step["table"]
        assert step["via"] == via, step["table"]
        assert step["note"] and step["note"].isascii() and "\n" not in step["note"]


def test_erase_order_deletes_children_before_trip_states():
    order = _order()
    pos = {t: i for i, t in enumerate(order)}
    assert pos["party_member"] < pos["trip_party"]
    for child in ("trip_party", "trip_node", "trip_edge", "trip_command", "signal", "event_log"):
        assert pos[child] < pos["trip_states"], child


def test_plan_erase_includes_user_id_on_every_step():
    plan = plan_erase(USER_ID)
    assert [s["table"] for s in plan] == _order()
    for planned, step in zip(plan, ERASE_STEPS):
        assert planned["user_id"] == USER_ID
        assert {k: v for k, v in planned.items() if k != "user_id"} == step
    # Copies: mutating the plan never changes ERASE_STEPS.
    plan[0]["table"] = "mutated"
    assert "user_id" not in ERASE_STEPS[0]
    assert ERASE_STEPS[0]["table"] == "party_member"


@pytest.mark.parametrize("bad", [None, "", "   ", "\t\n"])
def test_plan_erase_rejects_blank_user_id(bad):
    with pytest.raises(ValueError):
        plan_erase(bad)


def test_synthetic_identity_table_without_step_is_detected():
    rights = dict(RIGHTS_MAP)
    rights["synthetic_identity"] = {
        "identity": "direct_user_id",
        "export": "planned",
        "delete": "planned",
        "retention": "planned",
        "note": "Synthetic table for the guard.",
    }
    assert "synthetic_identity" in missing_erase_steps(rights=rights, steps=ERASE_STEPS)
    assert "synthetic_identity" not in RIGHTS_MAP
    assert "synthetic_identity" not in _order()


def test_module_imports_only_stdlib_and_data_rights():
    tree = ast.parse(Path(erase_module.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= {"__future__", "typing", "config"}, roots
    assert not roots & {"litellm", "supabase", "httpx", "psycopg", "psycopg2", "logging"}
