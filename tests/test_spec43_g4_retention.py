"""SPEC-43 Gap 4 slice R1: retention planner and bounded delete. No network.

Fixed now values only; no datetime.now() in this file.
"""

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config.data_rights import ERASE_EXEMPT_TABLES, RIGHTS_MAP
from services import data_rights_retention as retention
from services.data_rights_retention import (
    POLICIES,
    InMemoryRetentionBackend,
    RetentionPolicy,
    cutoff_for,
    run_retention,
    validate_policy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
USER = "user-g4-retention-7f3a"
CACHE = next(p for p in POLICIES if p.table == "cached_responses")
SIGNAL = next(p for p in POLICIES if p.table == "signal")


def _signal(sid, captured_at, user=USER):
    return {"signal_id": sid, "captured_at": captured_at, "user_id": user, "trip_id": "trip-r1"}


def _cache(cid, expires_at):
    return {"cache_id": cid, "expires_at": expires_at, "query_text": "private question text"}


def _report_table(report, table):
    return next(t for t in report.tables if t.table == table)


def test_cutoff_for_captured_at_policy_is_now_minus_365_days():
    assert SIGNAL.time_column == "captured_at"
    assert cutoff_for(SIGNAL, NOW) == NOW - timedelta(days=365)


def test_cutoff_for_expires_at_policy_is_now():
    assert CACHE.time_column == "expires_at"
    assert cutoff_for(CACHE, NOW) == NOW


def test_naive_datetime_raises_value_error():
    naive = datetime(2026, 11, 18, 12, 0, 0)
    with pytest.raises(ValueError):
        cutoff_for(SIGNAL, naive)
    with pytest.raises(ValueError):
        cutoff_for(CACHE, naive)
    with pytest.raises(ValueError):
        run_retention(InMemoryRetentionBackend(), now=naive)


def test_row_exactly_at_captured_at_cutoff_is_kept():
    cutoff = NOW - timedelta(days=365)
    backend = InMemoryRetentionBackend({"signal": [_signal("s-edge", cutoff)]})
    report = run_retention(backend, now=NOW, dry_run=False, policies=(SIGNAL,))
    row = _report_table(report, "signal")
    assert row.candidates == 0 and row.deleted == 0
    assert [r["signal_id"] for r in backend.tables["signal"]] == ["s-edge"]


def test_row_one_second_older_than_captured_at_cutoff_is_a_candidate():
    cutoff = NOW - timedelta(days=365)
    backend = InMemoryRetentionBackend(
        {"signal": [_signal("s-old", cutoff - timedelta(seconds=1)), _signal("s-edge", cutoff)]}
    )
    report = run_retention(backend, now=NOW, dry_run=False, policies=(SIGNAL,))
    row = _report_table(report, "signal")
    assert row.candidates == 1 and row.deleted == 1 and row.remaining is False
    assert [r["signal_id"] for r in backend.tables["signal"]] == ["s-edge"]


def test_expired_cached_responses_row_is_a_candidate_unexpired_is_kept():
    rows = [
        _cache("c-past", NOW - timedelta(seconds=1)),
        _cache("c-now", NOW),  # expires_at <= now: expired
        _cache("c-future", NOW + timedelta(seconds=1)),
    ]
    backend = InMemoryRetentionBackend({"cached_responses": rows})
    report = run_retention(backend, now=NOW, dry_run=False, policies=(CACHE,))
    row = _report_table(report, "cached_responses")
    assert row.candidates == 2 and row.deleted == 2
    assert [r["cache_id"] for r in backend.tables["cached_responses"]] == ["c-future"]

    # now far in the past: the cutoff is in the past, nothing is deleted.
    far_past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    backend = InMemoryRetentionBackend(
        {
            "cached_responses": [_cache("c-1", NOW - timedelta(days=30))],
            "signal": [_signal("s-1", NOW - timedelta(days=900))],
        }
    )
    report = run_retention(backend, now=far_past, dry_run=False)
    assert all(t.candidates == 0 and t.deleted == 0 for t in report.tables)
    assert len(backend.tables["cached_responses"]) == 1
    assert len(backend.tables["signal"]) == 1


def test_dry_run_deletes_nothing_and_reports_counts():
    backend = InMemoryRetentionBackend(
        {
            "cached_responses": [
                _cache("c-1", NOW - timedelta(hours=1)),
                _cache("c-2", NOW + timedelta(hours=1)),
            ],
            "signal": [
                _signal("s-1", NOW - timedelta(days=400)),
                _signal("s-2", NOW - timedelta(days=500)),
                _signal("s-3", NOW - timedelta(days=10)),
            ],
        }
    )
    before = json.dumps(backend.tables, default=str, sort_keys=True)
    report = run_retention(backend, now=NOW)  # dry_run defaults to True
    assert report.dry_run is True
    assert json.dumps(backend.tables, default=str, sort_keys=True) == before
    assert backend.deleted_keys == []
    cache, signal = _report_table(report, "cached_responses"), _report_table(report, "signal")
    assert (cache.candidates, cache.deleted, cache.remaining) == (1, 0, True)
    assert (signal.candidates, signal.deleted, signal.remaining) == (2, 0, True)
    assert report.now == NOW.isoformat()


def test_batch_limit_caps_deletes_per_policy_and_reports_remaining():
    old = [_signal(f"s-{i}", NOW - timedelta(days=400 + i)) for i in range(7)]
    expired = [_cache(f"c-{i}", NOW - timedelta(hours=i + 1)) for i in range(2)]
    backend = InMemoryRetentionBackend({"signal": old, "cached_responses": expired})

    first = run_retention(backend, now=NOW, dry_run=False, batch_limit=3)
    sig = _report_table(first, "signal")
    assert (sig.deleted, sig.remaining) == (3, True)
    cache = _report_table(first, "cached_responses")
    assert (cache.deleted, cache.remaining) == (2, False)

    second = run_retention(backend, now=NOW, dry_run=False, batch_limit=3)
    sig = _report_table(second, "signal")
    assert (sig.deleted, sig.remaining) == (3, True)
    third = run_retention(backend, now=NOW, dry_run=False, batch_limit=3)
    sig = _report_table(third, "signal")
    assert (sig.deleted, sig.remaining) == (1, False)
    assert backend.tables["signal"] == []


def test_batch_limit_outside_1_5000_raises_value_error():
    for bad in (0, -1, 5001, 10_000, True, 2.5, "500", None):
        with pytest.raises(ValueError):
            run_retention(InMemoryRetentionBackend(), now=NOW, batch_limit=bad)
    for ok in (1, 5000):  # the edges are inside the range
        run_retention(InMemoryRetentionBackend(), now=NOW, batch_limit=ok)


def test_deletion_order_is_oldest_first_then_primary_key():
    t1 = NOW - timedelta(days=500)
    t2 = NOW - timedelta(days=450)
    rows = [
        _signal("s-c", t2),
        _signal("s-b", t1),
        _signal("s-a", t1),
        _signal("s-d", NOW - timedelta(days=600)),
    ]
    backend = InMemoryRetentionBackend({"signal": rows})
    run_retention(backend, now=NOW, dry_run=False, batch_limit=2, policies=(SIGNAL,))
    run_retention(backend, now=NOW, dry_run=False, batch_limit=2, policies=(SIGNAL,))
    assert [k for _, k in backend.deleted_keys] == ["s-d", "s-a", "s-b", "s-c"]


def test_invalid_time_value_is_skipped_and_counted_never_deleted():
    rows = [
        _signal("s-none", None),
        _signal("s-text", "2020-01-01T00:00:00+00:00"),
        _signal("s-naive", datetime(2020, 1, 1)),
        {"signal_id": "s-missing", "user_id": USER},
        _signal("s-old", NOW - timedelta(days=400)),
    ]
    backend = InMemoryRetentionBackend({"signal": rows})
    report = run_retention(backend, now=NOW, dry_run=False, policies=(SIGNAL,))
    row = _report_table(report, "signal")
    assert row.skipped_invalid == 4
    assert row.candidates == 1 and row.deleted == 1
    left = {r["signal_id"] for r in backend.tables["signal"]}
    assert left == {"s-none", "s-text", "s-naive", "s-missing"}


def test_report_carries_no_user_ids_or_row_ids():
    backend = InMemoryRetentionBackend(
        {
            "cached_responses": [_cache("cache-secret-id-91", NOW - timedelta(hours=2))],
            "signal": [_signal("signal-secret-id-42", NOW - timedelta(days=400))],
        }
    )
    for dry in (True, False):
        report = run_retention(backend, now=NOW, dry_run=dry)
        text = json.dumps(report.to_dict(), sort_keys=True)
        for secret in (
            USER,
            "cache-secret-id-91",
            "signal-secret-id-42",
            "trip-r1",
            "private question text",
        ):
            assert secret not in text
        assert set(report.to_dict()) == {"now", "dry_run", "tables"}
        for t in report.to_dict()["tables"]:
            assert set(t) == {
                "table",
                "cutoff",
                "candidates",
                "deleted",
                "skipped_invalid",
                "remaining",
            }


def test_policy_on_data_rights_tombstone_is_rejected():
    with pytest.raises(ValueError):
        RetentionPolicy(
            table="data_rights_tombstone",
            time_column="created_at",
            window=timedelta(days=1),
            expiry_column=False,
        )
    with pytest.raises(ValueError):
        dataclasses.replace(SIGNAL, table="data_rights_tombstone")
    for table in ERASE_EXEMPT_TABLES:
        with pytest.raises(ValueError):
            dataclasses.replace(SIGNAL, table=table)
    # Even a policy that slipped past construction is rejected by the executor.
    bad = object.__new__(RetentionPolicy)
    for name, value in (
        ("table", "data_rights_tombstone"),
        ("time_column", "created_at"),
        ("window", timedelta(days=1)),
        ("expiry_column", False),
    ):
        object.__setattr__(bad, name, value)
    with pytest.raises(ValueError):
        validate_policy(bad)
    backend = InMemoryRetentionBackend(
        {"data_rights_tombstone": [{"id": "t1", "created_at": NOW - timedelta(days=9)}]}
    )
    with pytest.raises(ValueError):
        run_retention(backend, now=NOW, dry_run=False, policies=(bad,))
    assert len(backend.tables["data_rights_tombstone"]) == 1


def _retention_eligible(table):
    """Amendment 1 rule for a POLICIES table."""
    entry = RIGHTS_MAP.get(table)
    return (
        entry is not None
        and table not in ERASE_EXEMPT_TABLES
        and entry["identity"] != "erase_exempt"
        and entry["retention"] != "not_applicable"
    )


def test_every_policies_table_is_classified_in_rights_map_as_retention_eligible():
    assert {p.table for p in POLICIES} == {"cached_responses", "signal"}
    for policy in POLICIES:
        assert policy.table in RIGHTS_MAP, policy.table
        assert policy.table not in ERASE_EXEMPT_TABLES, policy.table
        assert RIGHTS_MAP[policy.table]["identity"] != "erase_exempt", policy.table
        assert RIGHTS_MAP[policy.table]["retention"] != "not_applicable", policy.table
        assert _retention_eligible(policy.table)
    # The rule excludes the tombstone and catalog tables.
    assert not _retention_eligible("data_rights_tombstone")
    for table, entry in RIGHTS_MAP.items():
        if entry["retention"] == "not_applicable":
            assert not _retention_eligible(table), table


class _SpyBackend:
    """Raises on any backend attribute other than the two allowed methods."""

    _ALLOWED = ("count_expired", "delete_expired")

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "calls", [])

    def __getattribute__(self, name):
        if name in _SpyBackend._ALLOWED:
            inner = object.__getattribute__(self, "_inner")
            calls = object.__getattribute__(self, "calls")
            method = getattr(inner, name)

            def _wrapped(*args, **kwargs):
                calls.append(name)
                return method(*args, **kwargs)

            return _wrapped
        if name in ("_inner", "calls", "__class__", "__dict__"):
            return object.__getattribute__(self, name)
        raise AssertionError(f"executor touched backend attribute {name!r}")


def test_executor_calls_only_count_expired_and_delete_expired_on_the_backend():
    inner = InMemoryRetentionBackend(
        {
            "cached_responses": [_cache("c-1", NOW - timedelta(hours=1))],
            "signal": [_signal("s-1", NOW - timedelta(days=400))],
        }
    )
    spy = _SpyBackend(inner)
    run_retention(spy, now=NOW)
    assert object.__getattribute__(spy, "calls") == ["count_expired", "count_expired"]
    object.__getattribute__(spy, "calls").clear()
    run_retention(spy, now=NOW, dry_run=False)
    assert set(object.__getattribute__(spy, "calls")) == {"count_expired", "delete_expired"}
    assert inner.tables["signal"] == [] and inner.tables["cached_responses"] == []


def test_hosted_safe_module_does_not_import_supabase_or_network_libraries():
    source = (REPO_ROOT / "services" / "data_rights_retention.py").read_text(encoding="utf-8")
    for needle in ("import supabase", "from supabase", "import httpx", "import requests"):
        assert needle not in source, needle
    assert source.isascii()
    assert "Windows are proposals subject to counsel review; hosted enablement is owner-only." in (
        retention.__doc__ or ""
    )
