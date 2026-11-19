"""SPEC-43 Gap 4 slice R2: Supabase retention backend against a fake client.

The fake extends the erase-test fake: it mimics the supabase-py PostgREST
builder (table / select(cols, count) / delete / eq / in_ / lt / lte / is_ /
order / limit / execute), stores rows per table, parses time filter values
with datetime.fromisoformat, and records every executed op. A delete with no
filters still runs in the fake and removes every row, so a regression is
visible. No network, no supabase package. Fixed now values only.
"""

import dataclasses
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import data_rights_retention_supabase as supa_module
from services.data_rights_retention import (
    POLICIES,
    InMemoryRetentionBackend,
    RetentionPolicy,
    run_retention,
)
from services.data_rights_retention_supabase import (
    BACKEND_ERROR_CODES,
    DELETE_CHUNK,
    PRIMARY_KEYS,
    RetentionBackendError,
    SupabaseRetentionBackend,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 19, 10, 0, 0, tzinfo=timezone.utc)
CACHE = next(p for p in POLICIES if p.table == "cached_responses")
SIGNAL = next(p for p in POLICIES if p.table == "signal")
SIGNAL_CUTOFF = NOW - timedelta(days=365)
SECRET = "secret-row-9f2c https://example.supabase.co/rest/v1/signal body=private"


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def _parse(value):
    return datetime.fromisoformat(value)


class _Query:
    def __init__(self, client, table):
        self._client = client
        self._table = table
        self._op = None
        self._cols = "*"
        self._count = None
        self._filters = []
        self._order = []
        self._limit = None

    def select(self, cols="*", count=None):
        self._op = "select"
        self._cols = cols
        self._count = count
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, tuple(vals)))
        return self

    def lt(self, col, val):
        self._filters.append(("lt", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _match(self, row):
        for kind, col, val in self._filters:
            have = row.get(col)
            if kind == "eq" and str(have) != str(val):
                return False
            if kind == "in" and str(have) not in {str(v) for v in val}:
                return False
            if kind == "lt" and (have is None or not have < _parse(val)):
                return False
            if kind == "lte" and (have is None or not have <= _parse(val)):
                return False
            if kind == "is" and val == "null" and have is not None:
                return False
        return True

    def execute(self):
        if self._op in self._client.fail_on:
            raise RuntimeError(SECRET)
        rows = self._client.store.setdefault(self._table, [])
        self._client.ops.append(
            {
                "table": self._table,
                "op": self._op,
                "filters": tuple(self._filters),
                "order": tuple(self._order),
                "limit": self._limit,
                "count": self._count,
                "cols": self._cols,
            }
        )
        hit = [r for r in rows if self._match(r)]
        if self._op == "delete":
            self._client.store[self._table] = [r for r in rows if not self._match(r)]
            return _Result([dict(r) for r in hit])
        for col, desc in reversed(self._order):
            hit.sort(key=lambda r, c=col: r.get(c), reverse=desc)
        total = len(hit)
        if self._limit is not None:
            hit = hit[: self._limit]
        if self._cols != "*":
            cols = [c.strip() for c in self._cols.split(",")]
            hit = [{c: r.get(c) for c in cols} for r in hit]
        else:
            hit = [dict(r) for r in hit]
        result = _Result(hit, count=total if self._count == "exact" else None)
        if self._client.after_select is not None:
            self._client.after_select(self._client)
        return result


class FakeClient:
    def __init__(self, fail_on=()):
        self.store = {}
        self.ops = []
        self.table_calls = 0
        self.fail_on = set(fail_on)
        self.after_select = None

    def table(self, name):
        self.table_calls += 1
        return _Query(self, name)

    def seed(self, table, row):
        self.store.setdefault(table, []).append(dict(row))


def _signal(sid, captured_at):
    return {"signal_id": sid, "captured_at": captured_at, "user_id": "u-r2", "trip_id": "t-r2"}


def _cache(cid, expires_at):
    return {"cache_id": cid, "expires_at": expires_at, "query_text": "private question"}


def _client(**tables):
    c = FakeClient()
    for table, rows in tables.items():
        for row in rows:
            c.seed(table, row)
    return c


def _ops(client, op):
    return [o for o in client.ops if o["op"] == op]


def _deleted_keys(client):
    keys = []
    for o in _ops(client, "delete"):
        for kind, _col, val in o["filters"]:
            if kind == "in":
                keys.extend((o["table"], k) for k in val)
    return keys


def _ids(client, table, pk):
    return [r[pk] for r in client.store.get(table, [])]


def test_count_for_cached_responses_uses_lte_on_expires_at():
    client = _client(
        cached_responses=[
            _cache("c-1", NOW - timedelta(hours=1)),
            _cache("c-2", NOW + timedelta(hours=1)),
        ]
    )
    counted = SupabaseRetentionBackend(client).count_expired(CACHE, NOW)
    assert counted.candidates == 1 and counted.skipped_invalid == 0
    first = _ops(client, "select")[0]
    assert first["table"] == "cached_responses" and first["count"] == "exact"
    assert first["cols"] == "cache_id" and first["limit"] == 1
    assert [(k, c) for k, c, _v in first["filters"]] == [("lte", "expires_at")]


def test_count_for_signal_uses_lt_on_captured_at():
    client = _client(signal=[_signal("s-1", NOW - timedelta(days=400))])
    counted = SupabaseRetentionBackend(client).count_expired(SIGNAL, SIGNAL_CUTOFF)
    assert counted.candidates == 1
    first = _ops(client, "select")[0]
    assert first["table"] == "signal" and first["count"] == "exact" and first["limit"] == 1
    assert [(k, c) for k, c, _v in first["filters"]] == [("lt", "captured_at")]


def test_signal_row_exactly_at_the_cutoff_is_kept():
    client = _client(
        signal=[
            _signal("s-edge", SIGNAL_CUTOFF),
            _signal("s-old", SIGNAL_CUTOFF - timedelta(seconds=1)),
        ]
    )
    backend = SupabaseRetentionBackend(client)
    assert backend.count_expired(SIGNAL, SIGNAL_CUTOFF).candidates == 1
    assert backend.delete_expired(SIGNAL, SIGNAL_CUTOFF, 10) == 1
    assert _ids(client, "signal", "signal_id") == ["s-edge"]


def test_cached_responses_row_expiring_exactly_now_is_a_candidate():
    client = _client(
        cached_responses=[_cache("c-now", NOW), _cache("c-later", NOW + timedelta(seconds=1))]
    )
    backend = SupabaseRetentionBackend(client)
    assert backend.count_expired(CACHE, NOW).candidates == 1
    assert backend.delete_expired(CACHE, NOW, 10) == 1
    assert _ids(client, "cached_responses", "cache_id") == ["c-later"]


def test_null_time_is_counted_as_skipped_and_never_deleted():
    client = _client(
        cached_responses=[
            _cache("c-null-1", None),
            _cache("c-null-2", None),
            _cache("c-old", NOW - timedelta(days=2)),
        ]
    )
    backend = SupabaseRetentionBackend(client)
    counted = backend.count_expired(CACHE, NOW)
    assert (counted.candidates, counted.skipped_invalid) == (1, 2)
    skip_op = _ops(client, "select")[1]
    assert [(k, c, v) for k, c, v in skip_op["filters"]] == [("is", "expires_at", "null")]
    assert backend.delete_expired(CACHE, NOW, 10) == 1
    assert sorted(_ids(client, "cached_responses", "cache_id")) == ["c-null-1", "c-null-2"]


def test_cutoff_is_sent_as_utc_with_z_suffix_and_no_plus_sign():
    plus_three = timezone(timedelta(hours=3))
    local = datetime(2026, 11, 19, 13, 0, 0, 123456, tzinfo=plus_three)  # 10:00:00.123456Z
    client = _client(cached_responses=[_cache("c-1", NOW - timedelta(days=1))])
    backend = SupabaseRetentionBackend(client)
    backend.count_expired(CACHE, local)
    backend.delete_expired(CACHE, local, 10)
    sent = [v for o in client.ops for k, _c, v in o["filters"] if k in ("lt", "lte")]
    assert sent and all(v == "2026-11-19T10:00:00.123456Z" for v in sent)
    pattern = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")
    assert all(pattern.match(v) and "+" not in v for v in sent)


def test_delete_takes_oldest_first_then_primary_key_at_most_limit_rows():
    t1 = NOW - timedelta(days=500)
    t2 = NOW - timedelta(days=450)
    client = _client(
        signal=[
            _signal("s-c", t2),
            _signal("s-b", t1),
            _signal("s-a", t1),
            _signal("s-d", NOW - timedelta(days=600)),
            _signal("s-new", NOW - timedelta(days=10)),
        ]
    )
    backend = SupabaseRetentionBackend(client)
    assert backend.delete_expired(SIGNAL, SIGNAL_CUTOFF, 3) == 3
    select = _ops(client, "select")[0]
    assert select["order"] == (("captured_at", False), ("signal_id", False))
    assert select["limit"] == 3 and select["cols"] == "signal_id,captured_at"
    assert [k for _t, k in _deleted_keys(client)] == ["s-d", "s-a", "s-b"]
    assert sorted(_ids(client, "signal", "signal_id")) == ["s-c", "s-new"]


def test_every_delete_carries_a_primary_key_in_filter_and_the_time_filter():
    client = _client(
        signal=[_signal(f"s-{i}", NOW - timedelta(days=400 + i)) for i in range(5)],
        cached_responses=[_cache(f"c-{i}", NOW - timedelta(hours=i + 1)) for i in range(3)],
    )
    run_retention(SupabaseRetentionBackend(client), now=NOW, dry_run=False, batch_limit=2)
    deletes = _ops(client, "delete")
    assert deletes
    for o in deletes:
        pk = PRIMARY_KEYS[o["table"]]
        kinds = {(k, c) for k, c, _v in o["filters"]}
        in_filters = [v for k, c, v in o["filters"] if k == "in" and c == pk]
        assert in_filters and all(len(v) > 0 for v in in_filters), o
        if o["table"] == "cached_responses":
            expected = ("lte", "expires_at")
        else:
            expected = ("lt", "captured_at")
        assert expected in kinds, o


def test_no_candidates_sends_no_delete():
    client = _client(
        signal=[_signal("s-new", NOW - timedelta(days=1))],
        cached_responses=[_cache("c-fresh", NOW + timedelta(hours=5))],
    )
    backend = SupabaseRetentionBackend(client)
    assert backend.delete_expired(SIGNAL, SIGNAL_CUTOFF, 100) == 0
    assert backend.delete_expired(CACHE, NOW, 100) == 0
    assert _ops(client, "delete") == []
    assert len(client.store["signal"]) == 1 and len(client.store["cached_responses"]) == 1


def test_delete_chunks_primary_keys_at_delete_chunk():
    total = DELETE_CHUNK * 2 + 50
    client = _client(
        signal=[_signal(f"s-{i:04d}", NOW - timedelta(days=400, minutes=i)) for i in range(total)]
    )
    backend = SupabaseRetentionBackend(client)
    assert backend.delete_expired(SIGNAL, SIGNAL_CUTOFF, total) == total
    sizes = [len(v) for o in _ops(client, "delete") for k, _c, v in o["filters"] if k == "in"]
    assert sizes == [DELETE_CHUNK, DELETE_CHUNK, 50]
    assert client.store["signal"] == []


def test_row_whose_time_moved_after_the_select_is_not_deleted():
    client = _client(
        signal=[
            _signal("s-moved", NOW - timedelta(days=500)),
            _signal("s-old", NOW - timedelta(days=400)),
        ]
    )

    def _touch(c):
        for row in c.store["signal"]:
            if row["signal_id"] == "s-moved":
                row["captured_at"] = NOW  # re-captured after the select
        c.after_select = None

    client.after_select = _touch
    deleted = SupabaseRetentionBackend(client).delete_expired(SIGNAL, SIGNAL_CUTOFF, 10)
    assert deleted == 1
    assert _ids(client, "signal", "signal_id") == ["s-moved"]


def test_invalid_limit_naive_cutoff_or_unknown_policy_makes_no_client_call():
    client = _client(signal=[_signal("s-1", NOW - timedelta(days=400))])
    backend = SupabaseRetentionBackend(client)
    for bad in (0, -1, 5001, True, 2.5, "10", None):
        with pytest.raises(ValueError):
            backend.delete_expired(SIGNAL, SIGNAL_CUTOFF, bad)
    naive = datetime(2026, 11, 19, 10, 0, 0)
    with pytest.raises(ValueError):
        backend.count_expired(SIGNAL, naive)
    with pytest.raises(ValueError):
        backend.delete_expired(SIGNAL, naive, 10)

    tombstone = object.__new__(RetentionPolicy)
    for name, value in (
        ("table", "data_rights_tombstone"),
        ("time_column", "created_at"),
        ("window", timedelta(days=1)),
        ("expiry_column", False),
    ):
        object.__setattr__(tombstone, name, value)
    third_table = RetentionPolicy(
        table="trip_states",
        time_column="updated_at",
        window=timedelta(days=30),
        expiry_column=False,
    )
    other_window = dataclasses.replace(SIGNAL, window=timedelta(days=30))
    for policy in (tombstone, third_table, other_window):
        with pytest.raises(ValueError):
            backend.count_expired(policy, SIGNAL_CUTOFF)
        with pytest.raises(ValueError):
            backend.delete_expired(policy, SIGNAL_CUTOFF, 10)
    assert client.ops == [] and client.table_calls == 0
    assert _ids(client, "signal", "signal_id") == ["s-1"]


def test_client_failure_raises_a_closed_code_with_no_row_data_in_the_message(monkeypatch):
    rows = {"signal": [_signal("secret-row-9f2c", NOW - timedelta(days=400))]}
    def _count(b):
        return b.count_expired(SIGNAL, SIGNAL_CUTOFF)

    def _delete(b):
        return b.delete_expired(SIGNAL, SIGNAL_CUTOFF, 10)

    cases = (
        ("select", _count, "retention_count_failed"),
        ("select", _delete, "retention_delete_failed"),
        ("delete", _delete, "retention_delete_failed"),
    )
    for fail_on, call, code in cases:
        client = FakeClient(fail_on={fail_on})
        for row in rows["signal"]:
            client.seed("signal", row)
        with pytest.raises(RetentionBackendError) as err:
            call(SupabaseRetentionBackend(client))
        assert err.value.code == code and str(err.value) == code
        assert code in BACKEND_ERROR_CODES
        assert err.value.__cause__ is None and err.value.__suppress_context__ is True
        for leak in ("secret-row-9f2c", "supabase.co", "body=private", "signal_id"):
            assert leak not in str(err.value) and leak not in repr(err.value)
    # A missing count is a count failure, never a len(data) fallback.
    client = _client(signal=rows["signal"])
    original = _Query.execute

    def _without_count(self):
        result = original(self)
        result.count = None
        return result

    monkeypatch.setattr(_Query, "execute", _without_count)
    with pytest.raises(RetentionBackendError) as err:
        SupabaseRetentionBackend(client).count_expired(SIGNAL, SIGNAL_CUTOFF)
    assert err.value.code == "retention_count_failed"
    assert _ops(client, "select")  # the client was asked; data rows were not counted


def _rows_for_parity():
    signal = [
        _signal("s-03", NOW - timedelta(days=700)),
        _signal("s-01", NOW - timedelta(days=500)),
        _signal("s-02", NOW - timedelta(days=500)),
        _signal("s-04", SIGNAL_CUTOFF),
        _signal("s-05", SIGNAL_CUTOFF - timedelta(seconds=1)),
        _signal("s-06", NOW - timedelta(days=30)),
        _signal("s-07", NOW - timedelta(days=366)),
    ]
    cache = [
        _cache("c-03", NOW - timedelta(hours=5)),
        _cache("c-01", NOW),
        _cache("c-02", NOW - timedelta(hours=5)),
        _cache("c-04", NOW + timedelta(seconds=1)),
        _cache("c-05", None),
    ]
    return {"signal": signal, "cached_responses": cache}


def test_parity_with_the_in_memory_backend_for_the_same_rows():
    rows = _rows_for_parity()
    memory = InMemoryRetentionBackend({t: [dict(r) for r in rs] for t, rs in rows.items()})
    client = _client(**{t: [dict(r) for r in rs] for t, rs in rows.items()})
    supa = SupabaseRetentionBackend(client)

    dry_mem = run_retention(memory, now=NOW)
    dry_supa = run_retention(supa, now=NOW)
    assert dry_mem.to_dict() == dry_supa.to_dict()
    assert _ops(client, "delete") == []

    for _ in range(10):
        real_mem = run_retention(memory, now=NOW, dry_run=False, batch_limit=2)
        real_supa = run_retention(supa, now=NOW, dry_run=False, batch_limit=2)
        assert real_mem.to_dict() == real_supa.to_dict()
        if not any(t.remaining for t in real_mem.tables):
            break
    assert memory.deleted_keys == _deleted_keys(client)
    assert [k for _t, k in memory.deleted_keys] == [
        "c-02",
        "c-03",
        "s-03",
        "s-01",
        "c-01",
        "s-02",
        "s-07",
        "s-05",
    ]
    for table, pk in PRIMARY_KEYS.items():
        assert sorted(r[pk] for r in memory.tables[table]) == sorted(_ids(client, table, pk))


def test_dry_run_through_run_retention_sends_no_delete():
    rows = _rows_for_parity()
    client = _client(**rows)
    report = run_retention(SupabaseRetentionBackend(client), now=NOW)
    assert report.dry_run is True
    assert _ops(client, "delete") == []
    assert {o["op"] for o in client.ops} == {"select"}
    assert len(client.store["signal"]) == len(rows["signal"])
    assert len(client.store["cached_responses"]) == len(rows["cached_responses"])


def test_primary_keys_match_the_in_memory_backend():
    assert PRIMARY_KEYS == InMemoryRetentionBackend.PRIMARY_KEYS
    assert set(PRIMARY_KEYS) == {p.table for p in POLICIES}


def test_hosted_safe_module_does_not_import_supabase_network_or_logging():
    source = Path(supa_module.__file__).read_text(encoding="utf-8")
    for needle in (
        "import supabase",
        "from supabase",
        "import httpx",
        "import requests",
        "import logging",
        "print(",
    ):
        assert needle not in source, needle
    assert source.isascii()
    sentence = (
        "Not wired to any route, scheduler or CLI; any hosted run is an owner decision "
        "before production."
    )
    assert sentence in (supa_module.__doc__ or "")
    # Only public names from R1 are imported.
    assert "from services.data_rights_retention import" in source
    assert not re.search(r"data_rights_retention import \(?[^)]*\b_\w+", source)


def test_module_is_not_wired_to_any_route_scheduler_or_main():
    module_path = Path(supa_module.__file__).resolve()
    skip_parts = {"tests", ".git", "node_modules", ".venv", "venv", "build", "mobile"}
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        resolved = path.resolve()
        if resolved == module_path:
            continue
        rel = resolved.relative_to(REPO_ROOT.resolve())
        if skip_parts & set(rel.parts) or any(p.startswith(".") for p in rel.parts):
            continue
        if "data_rights_retention_supabase" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(rel))
    assert offenders == []
