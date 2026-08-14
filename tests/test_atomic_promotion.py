"""Tests for atomic identity_kind promotion in SupabaseService.

Structural assertions (not behavioral): the UPDATE statement must carry an
.in_("identity_kind", lower_kinds) filter so that a losing interleave writes
zero rows instead of the wrong value. Behavioral tests live in
test_identity_kind_upgrade.py; these prove the correctness mechanism is in
the statement, not just the Python branch.
"""

import uuid
import sys
import os
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _fresh_uid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Instrumented FakeClient that records .in_() calls
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, data):
        self.data = data


class InstrumentedFakeTable:
    """Records all .in_() filter arguments passed to UPDATE chains."""

    def __init__(self):
        self._rows = {}
        self._pending_op = None
        self._filter_uid = None
        self._update_payload = None
        self._in_filter = None  # (column, values) from last .in_() call
        self.update_calls = []  # list of {payload, eq_uid, in_filter}
        self._stale_read = None  # one-shot override for SELECT (simulates stale snapshot)

    def table(self, name):
        self._pending_op = None
        self._filter_uid = None
        self._update_payload = None
        self._in_filter = None
        return self

    def select(self, cols):
        self._pending_op = "select"
        return self

    def eq(self, col, val):
        self._filter_uid = val
        return self

    def in_(self, col, values):
        self._in_filter = (col, list(values))
        return self

    def execute(self):
        if self._pending_op == "select":
            if self._stale_read is not None:
                # One-shot: return a row with overridden fields (simulates
                # a stale snapshot from a losing thread). Consumed once so it
                # cannot leak into subsequent calls in the same test.
                row = dict(self._rows.get(self._filter_uid, {}))
                row.update(self._stale_read)
                self._stale_read = None
                self._pending_op = None
                return FakeResponse([row] if row else [])
            row = self._rows.get(self._filter_uid)
            self._pending_op = None
            return FakeResponse([row] if row else [])
        elif self._pending_op == "insert":
            self._rows[self._insert_data["user_id"]] = dict(self._insert_data)
            self._pending_op = None
            return FakeResponse([self._insert_data])
        elif self._pending_op == "update":
            self.update_calls.append(
                {
                    "payload": self._update_payload,
                    "eq_uid": self._filter_uid,
                    "in_filter": self._in_filter,
                }
            )
            # Simulate Postgres semantics: if .in_() was called, only apply
            # when the stored value is in the allowed set. If .in_() was NOT
            # called, the UPDATE is unconditional (matches any row with eq).
            if self._filter_uid in self._rows:
                if self._in_filter:
                    col, allowed = self._in_filter
                    stored_val = self._rows[self._filter_uid].get(col)
                    if stored_val in allowed:
                        self._rows[self._filter_uid].update(self._update_payload)
                else:
                    # No in_ filter: unconditional update (real Postgres behavior)
                    self._rows[self._filter_uid].update(self._update_payload)
            self._pending_op = None
            return FakeResponse([])
        return FakeResponse([])

    def insert(self, data):
        self._pending_op = "insert"
        self._insert_data = data
        return self

    def update(self, data):
        self._pending_op = "update"
        self._update_payload = data
        return self


def _make_svc():
    """Create a SupabaseService with an InstrumentedFakeTable."""
    os.environ["TB_SUPABASE_URL"] = "https://fake.supabase.co"
    os.environ["TB_SUPABASE_KEY"] = "fake-key"
    try:
        import services.supabase_service as ss_mod

        importlib.reload(ss_mod)
        svc = ss_mod.SupabaseService.__new__(ss_mod.SupabaseService)
        svc._client = InstrumentedFakeTable()
        return svc
    finally:
        os.environ.pop("TB_SUPABASE_URL", None)
        os.environ.pop("TB_SUPABASE_KEY", None)


# ---------------------------------------------------------------------------
# Structural: UPDATE carries .in_ filter with exactly the lower kinds
# ---------------------------------------------------------------------------


class TestAtomicPromotionFilter:
    """The promotion UPDATE must filter on strictly-lower kinds via .in_()."""

    def test_anonymous_promotion_filters_on_unknown_only(self):
        """Promoting to anonymous: in_ filter must be ['unknown']."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)  # creates as 'unknown'
        svc._client.update_calls.clear()
        svc.get_or_create_user(uid, identity_kind="anonymous")

        assert len(svc._client.update_calls) == 1
        call = svc._client.update_calls[0]
        assert call["in_filter"] is not None, "UPDATE missing .in_ filter"
        col, values = call["in_filter"]
        assert col == "identity_kind"
        assert sorted(values) == ["unknown"]

    def test_supabase_promotion_filters_on_unknown_and_anonymous(self):
        """Promoting to supabase: in_ filter must be ['anonymous', 'unknown']."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)  # creates as 'unknown'
        svc._client.update_calls.clear()
        svc.get_or_create_user(uid, identity_kind="supabase")

        assert len(svc._client.update_calls) == 1
        call = svc._client.update_calls[0]
        assert call["in_filter"] is not None, "UPDATE missing .in_ filter"
        col, values = call["in_filter"]
        assert col == "identity_kind"
        assert sorted(values) == ["anonymous", "unknown"]

    def test_supabase_from_anonymous_filters_on_unknown_and_anonymous(self):
        """anonymous -> supabase: in_ filter still names both lower kinds."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="anonymous")
        svc._client.update_calls.clear()
        svc.get_or_create_user(uid, identity_kind="supabase")

        assert len(svc._client.update_calls) == 1
        call = svc._client.update_calls[0]
        assert call["in_filter"] is not None, "UPDATE missing .in_ filter"
        col, values = call["in_filter"]
        assert col == "identity_kind"
        assert sorted(values) == ["anonymous", "unknown"]

    def test_bare_unknown_issues_no_update(self):
        """A bare call (identity_kind='unknown') must never issue an UPDATE."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="anonymous")
        svc._client.update_calls.clear()
        svc.get_or_create_user(uid)  # bare, default 'unknown'

        assert len(svc._client.update_calls) == 0

    def test_same_kind_issues_no_update(self):
        """Calling with the same kind as stored must not issue an UPDATE."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc._client.update_calls.clear()
        svc.get_or_create_user(uid, identity_kind="supabase")

        assert len(svc._client.update_calls) == 0

    def test_downgrade_issues_no_update(self):
        """A lower-rank kind (supabase -> anonymous) must not issue an UPDATE."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc._client.update_calls.clear()
        svc.get_or_create_user(uid, identity_kind="anonymous")

        assert len(svc._client.update_calls) == 0


# ---------------------------------------------------------------------------
# Behavioral: the in_ filter prevents stale-read downgrades
# ---------------------------------------------------------------------------


class TestAtomicBehavior:
    """The in_ filter must actually prevent writes when the real row has advanced.

    Uses _stale_read to simulate the race: the SELECT returns old data (the
    loser's snapshot), the Python check fires, the UPDATE is issued -- but the
    .in_() filter matches zero rows because the real stored value is higher.
    """

    def test_race_loser_writes_nothing(self):
        """Loser thread issues UPDATE but in_ filter prevents the write."""
        svc = _make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)  # stored: unknown

        # Winner thread already promoted to supabase (behind loser's back).
        svc._client._rows[uid]["identity_kind"] = "supabase"

        # Loser's SELECT will return stale snapshot showing 'unknown'.
        svc._client._stale_read = {"identity_kind": "unknown"}
        svc._client.update_calls.clear()

        svc.get_or_create_user(uid, identity_kind="anonymous")

        # The loser does not know it lost: Python sees rank 1 > 0 from
        # the stale read and issues the UPDATE. But the .in_() filter
        # names only ['unknown'], the real row is 'supabase', so zero
        # rows are updated.
        assert len(svc._client.update_calls) == 1, (
            "Loser must issue an UPDATE (proves Python check fired)"
        )
        assert svc._client._rows[uid]["identity_kind"] == "supabase", (
            "Row must stay supabase (proves .in_() filter blocked the write)"
        )
