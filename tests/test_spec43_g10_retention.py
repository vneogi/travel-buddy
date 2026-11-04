"""SPEC-43 Gap 10 retention: the in-memory error ring drops expired entries.

Timestamps are set explicitly relative to now (no frozen calendar date).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from main import app
from monitoring.error_log import ERROR_RING_TTL_HOURS, ErrorLog, error_log

CANARY_TOKEN = "g10-admin-canary-token"


@pytest.fixture(autouse=True)
def _clear_ring():
    error_log.clear()
    yield
    error_log.clear()


def _record(log, request_id):
    log.record(
        request_id=request_id,
        method="GET",
        path="/g10/retention",
        status=500,
        exc_type="RuntimeError",
        message=f"boom {request_id}",
        traceback_str=f"Traceback for {request_id}",
    )


def _set_ts(log, request_id, ts):
    # Reach the stored dict directly so no public method purges first.
    for entry in log._entries:
        if entry["request_id"] == request_id:
            entry["ts"] = ts
            return
    raise AssertionError(f"{request_id} not in ring")


def _expired_ts():
    old = datetime.now(timezone.utc) - timedelta(hours=ERROR_RING_TTL_HOURS, minutes=5)
    return old.isoformat()


def test_ttl_constant_is_24_hours():
    assert ERROR_RING_TTL_HOURS == 24


def test_error_ring_drops_expired_entries_on_recent():
    _record(error_log, "req-g10-expired")
    _record(error_log, "req-g10-fresh")
    _set_ts(error_log, "req-g10-expired", _expired_ts())

    recent = error_log.recent()
    ids = [e["request_id"] for e in recent]
    assert "req-g10-expired" not in ids
    assert ids == ["req-g10-fresh"]
    assert error_log.count() == 1
    assert "req-g10-expired" not in json.dumps(error_log.recent())


def test_error_ring_drops_expired_entries_on_record():
    _record(error_log, "req-g10-old")
    _set_ts(error_log, "req-g10-old", _expired_ts())
    _record(error_log, "req-g10-new")

    # Inspect the deque directly: record itself must have purged.
    assert [e["request_id"] for e in error_log._entries] == ["req-g10-new"]
    assert error_log.count() == 1
    assert [e["request_id"] for e in error_log.recent()] == ["req-g10-new"]


def test_count_purges_without_recent():
    log = ErrorLog()
    _record(log, "req-a")
    _record(log, "req-b")
    _set_ts(log, "req-a", _expired_ts())
    assert log.count() == 1
    assert [e["request_id"] for e in log._entries] == ["req-b"]


@pytest.mark.parametrize("bad_ts", ["not-a-timestamp", "", None, 12345])
def test_unparseable_or_missing_ts_is_dropped(bad_ts):
    log = ErrorLog()
    _record(log, "req-bad")
    _record(log, "req-good")
    _set_ts(log, "req-bad", bad_ts)
    assert [e["request_id"] for e in log.recent()] == ["req-good"]
    assert log.count() == 1


def test_missing_ts_key_is_dropped():
    log = ErrorLog()
    _record(log, "req-nokey")
    _record(log, "req-good")
    for entry in log._entries:
        if entry["request_id"] == "req-nokey":
            del entry["ts"]
    assert log.count() == 1


def test_naive_ts_is_treated_as_utc():
    log = ErrorLog()
    _record(log, "req-naive-fresh")
    _record(log, "req-naive-old")
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    _set_ts(log, "req-naive-fresh", (now_naive - timedelta(hours=1)).isoformat())
    old = now_naive - timedelta(hours=ERROR_RING_TTL_HOURS, minutes=5)
    _set_ts(log, "req-naive-old", old.isoformat())
    assert [e["request_id"] for e in log.recent()] == ["req-naive-fresh"]


def test_entry_inside_ttl_is_kept():
    log = ErrorLog()
    _record(log, "req-recent")
    inside = datetime.now(timezone.utc) - timedelta(hours=ERROR_RING_TTL_HOURS - 1)
    _set_ts(log, "req-recent", inside.isoformat())
    assert log.count() == 1


def test_cap_still_applies_after_purge():
    log = ErrorLog()
    for i in range(5):
        _record(log, f"req-{i}")
    _set_ts(log, "req-0", _expired_ts())
    assert log.count() == 4
    for i in range(5, 150):
        _record(log, f"req-{i}")
    assert log.count() == 100
    assert log.recent(limit=1)[0]["request_id"] == "req-149"


def test_debug_get_count_matches_purged_errors(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "debug_admin_token", CANARY_TOKEN)
    _record(error_log, "req-http-expired")
    _record(error_log, "req-http-fresh")
    _set_ts(error_log, "req-http-expired", _expired_ts())

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/debug/errors", headers={"X-Debug-Admin-Token": CANARY_TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert [e["request_id"] for e in body["errors"]] == ["req-http-fresh"]
    assert "req-http-expired" not in r.text
