"""SPEC-43 Gap 4 slice 3: execute_erase walks the plan against a backend.

A recording backend stands in for the database. No SQL, no network.
"""

import pytest

from config.data_rights import RIGHTS_MAP
from services.data_rights_erase import (
    ERASE_STEPS,
    UnknownEraseMethodError,
    execute_erase,
    plan_erase,
)

USER_ID = "user-g4-exec-7b21"
CANARY = "ERASE-CANARY-g4-stop"
NONE_IDENTITY = {t for t, e in RIGHTS_MAP.items() if e["identity"] == "none"}


class RecordingBackend:
    """Stores (method_name, user_id, table) and returns 1 row."""

    def __init__(self, fail_on=None, error=None):
        self.calls = []
        self.fail_on = fail_on
        self.error = error

    def _record(self, method_name, user_id, table):
        self.calls.append((method_name, user_id, table))
        if table == self.fail_on:
            raise self.error
        return 1

    def delete_where_user_id(self, user_id, table):
        return self._record("delete_where_user_id", user_id, table)

    def delete_via_trip_states(self, user_id, table):
        return self._record("delete_via_trip_states", user_id, table)

    def delete_via_party(self, user_id, table):
        return self._record("delete_via_party", user_id, table)


def test_execute_erase_calls_backend_in_plan_order():
    backend = RecordingBackend()
    results = execute_erase(USER_ID, backend)
    assert [table for _m, _u, table in backend.calls] == [s["table"] for s in ERASE_STEPS]
    assert [m for m, _u, _t in backend.calls] == [s["method"] for s in ERASE_STEPS]
    assert all(u == USER_ID for _m, u, _t in backend.calls)
    assert "cached_responses" not in [t for _m, _u, t in backend.calls]
    assert results == [
        {"table": s["table"], "method": s["method"], "via": s["via"], "rows": 1}
        for s in ERASE_STEPS
    ]


def test_execute_erase_stops_after_first_backend_error():
    error = RuntimeError(CANARY)
    backend = RecordingBackend(fail_on="trip_party", error=error)
    with pytest.raises(RuntimeError) as excinfo:
        execute_erase(USER_ID, backend)
    assert excinfo.value is error
    assert [t for _m, _u, t in backend.calls] == ["party_member", "trip_party"]
    called = {t for _m, _u, t in backend.calls}
    assert "trip_states" not in called
    assert not called & {s["table"] for s in ERASE_STEPS[2:]}


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_execute_erase_rejects_blank_user_id_before_backend(bad):
    backend = RecordingBackend()
    with pytest.raises(ValueError):
        execute_erase(bad, backend)
    with pytest.raises(ValueError):
        execute_erase(bad, backend, steps=list(ERASE_STEPS))
    assert backend.calls == []


@pytest.mark.parametrize("position", [0, 1, len(ERASE_STEPS) - 1])
def test_execute_erase_unknown_method_does_not_call_backend(position):
    steps = plan_erase(USER_ID)
    steps[position] = dict(steps[position], method="delete_everywhere")
    backend = RecordingBackend()
    with pytest.raises(UnknownEraseMethodError):
        execute_erase(USER_ID, backend, steps=steps)
    assert backend.calls == []
    assert issubclass(UnknownEraseMethodError, ValueError)
    assert "delete_everywhere" not in {s["method"] for s in ERASE_STEPS}


def test_recording_backend_never_sees_catalog_tables():
    backend = RecordingBackend()
    execute_erase(USER_ID, backend)
    called = {t for _m, _u, t in backend.calls}
    assert NONE_IDENTITY, "no none-identity tables in RIGHTS_MAP"
    assert not called & NONE_IDENTITY
    assert {"venues_rag", "cached_responses"} <= NONE_IDENTITY


def test_execute_erase_does_not_print(capsys):
    execute_erase(USER_ID, RecordingBackend())
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
