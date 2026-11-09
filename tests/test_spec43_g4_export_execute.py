"""SPEC-43 Gap 4 slice 11: execute_export walks the plan on a fake backend."""

import ast
from pathlib import Path

import pytest

from config.data_rights import RIGHTS_MAP
from services import data_rights_export as export_module
from services.data_rights_export import (
    EXPORT_METHODS,
    EXPORT_STEPS,
    UnknownExportMethodError,
    execute_export,
)

USER = "user-g4-export-exec-3b7a"
STOP_CANARY = "EXPORT-CANARY-g4-stop"


class RecordingBackend:
    """Records (method, user_id, table); returns [{"seed": table}] or []."""

    def __init__(self, fail_on=None, error=None, empty=()):
        self.calls = []
        self.fail_on = fail_on
        self.error = error
        self.empty = set(empty)

    def _fetch(self, method, user_id, table):
        self.calls.append((method, user_id, table))
        if table == self.fail_on:
            raise self.error
        return [] if table in self.empty else [{"seed": table}]

    def fetch_where_user_id(self, user_id, table):
        return self._fetch("fetch_where_user_id", user_id, table)

    def fetch_via_trip_states(self, user_id, table):
        return self._fetch("fetch_via_trip_states", user_id, table)

    def fetch_via_party(self, user_id, table):
        return self._fetch("fetch_via_party", user_id, table)


def _expected():
    return [(s["method"], s["table"]) for s in EXPORT_STEPS]


def test_execute_export_calls_backend_in_plan_order():
    backend = RecordingBackend(empty={"signal"})
    results = execute_export(USER, backend)
    assert [(m, t) for m, _u, t in backend.calls] == _expected()
    assert {u for _m, u, _t in backend.calls} == {USER}
    called = [t for _m, _u, t in backend.calls]
    assert "cached_responses" not in called
    assert not {t for t, e in RIGHTS_MAP.items() if e["identity"] == "none"} & set(called)
    assert [r["table"] for r in results] == [s["table"] for s in EXPORT_STEPS]
    for result, step in zip(results, EXPORT_STEPS):
        assert set(result) == {"table", "method", "via", "rows"}
        assert (result["method"], result["via"]) == (step["method"], step["via"])
        expected_rows = [] if step["table"] == "signal" else [{"seed": step["table"]}]
        assert result["rows"] == expected_rows
        assert isinstance(result["rows"], list)


def test_execute_export_stops_after_first_backend_error():
    assert EXPORT_STEPS[2]["table"] == "trip_node"
    err = RuntimeError(STOP_CANARY)
    backend = RecordingBackend(fail_on="trip_node", error=err)
    with pytest.raises(RuntimeError) as excinfo:
        execute_export(USER, backend)
    assert excinfo.value is err
    assert [t for _m, _u, t in backend.calls] == ["user_tiers", "trip_states", "trip_node"]
    later = {s["table"] for s in EXPORT_STEPS[3:]}
    assert not later & {t for _m, _u, t in backend.calls}


@pytest.mark.parametrize("bad", [None, "", "   ", 42, b"user"])
def test_execute_export_rejects_blank_user_id_before_backend(bad):
    backend = RecordingBackend()
    with pytest.raises(ValueError):
        execute_export(bad, backend)
    assert backend.calls == []


@pytest.mark.parametrize("position", [0, 4, -1])
def test_execute_export_unknown_method_before_any_backend_call(position):
    steps = [dict(s) for s in EXPORT_STEPS]
    steps[position]["method"] = "delete_where_user_id"
    backend = RecordingBackend()
    with pytest.raises(UnknownExportMethodError):
        execute_export(USER, backend, steps=steps)
    assert backend.calls == []
    assert issubclass(UnknownExportMethodError, ValueError)
    assert "delete_where_user_id" not in EXPORT_METHODS


def test_execute_export_result_rows_are_detached_copies():
    store_row = {"id": 1, "note": "original"}
    returned = [store_row]

    class KeepingBackend(RecordingBackend):
        def fetch_where_user_id(self, user_id, table):
            self.calls.append(("fetch_where_user_id", user_id, table))
            return returned

    backend = KeepingBackend()
    step = next(s for s in EXPORT_STEPS if s["method"] == "fetch_where_user_id")
    results = execute_export(USER, backend, steps=[step])
    rows = results[0]["rows"]
    assert rows == [{"id": 1, "note": "original"}]
    assert rows is not returned and rows[0] is not store_row
    rows[0]["note"] = "mutated by caller"
    rows.append({"id": 2})
    assert store_row == {"id": 1, "note": "original"}
    assert returned == [store_row]
    store_row["note"] = "mutated by backend"
    assert rows[0]["note"] == "mutated by caller"


def test_execute_export_accepts_explicit_steps_override():
    step = {"table": "trip_party", "method": "fetch_via_trip_states", "via": "x", "note": "n"}
    backend = RecordingBackend()
    results = execute_export(USER, backend, steps=[step])
    assert backend.calls == [("fetch_via_trip_states", USER, "trip_party")]
    assert results == [
        {
            "table": "trip_party",
            "method": "fetch_via_trip_states",
            "via": "x",
            "rows": [{"seed": "trip_party"}],
        }
    ]


def test_export_execute_module_has_no_supabase_import(capsys):
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
    assert "print(" not in source and "open(" not in source
    execute_export(USER, RecordingBackend())
    out = capsys.readouterr()
    assert USER not in out.out and USER not in out.err
