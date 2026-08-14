"""Tests for identity_kind upgrade-on-sight (both backends, R13).

The identity_kind column must upgrade monotonically:
  unknown (0) < anonymous (1) < supabase (2)

A bare call with identity_kind='unknown' (the default for internal callers
that do not know the kind) must NEVER overwrite a stored value. A higher-rank
kind always promotes. A lower-rank kind is always a no-op.
"""

import uuid
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _fresh_uid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# In-memory backend (DatabaseService)
# ---------------------------------------------------------------------------

class TestUpgradeOnSightInMemory:
    """Upgrade-on-sight in the in-memory DatabaseService."""

    def _make_svc(self):
        from services.database_service import DatabaseService
        return DatabaseService()

    def test_ordering_independence_bare_then_anonymous(self):
        """User created via bare path (unknown), then router with anonymous -> upgrades."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)  # bare internal caller, default 'unknown'
        assert svc._users[uid]["identity_kind"] == "unknown"
        svc.get_or_create_user(uid, identity_kind="anonymous")
        assert svc._users[uid]["identity_kind"] == "anonymous"

    def test_ordering_independence_bare_then_supabase(self):
        """User created via bare path (unknown), then router with supabase -> upgrades."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)
        svc.get_or_create_user(uid, identity_kind="supabase")
        assert svc._users[uid]["identity_kind"] == "supabase"

    def test_monotonicity_known_then_bare(self):
        """Once anonymous is stored, a bare call must NOT overwrite to unknown."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="anonymous")
        svc.get_or_create_user(uid)  # bare call, default 'unknown'
        assert svc._users[uid]["identity_kind"] == "anonymous"

    def test_monotonicity_supabase_then_bare(self):
        """Once supabase is stored, a bare call must NOT overwrite."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc.get_or_create_user(uid)
        assert svc._users[uid]["identity_kind"] == "supabase"

    def test_transition_anonymous_to_supabase(self):
        """A user who starts anonymous and later signs in ends as supabase."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="anonymous")
        svc.get_or_create_user(uid, identity_kind="supabase")
        assert svc._users[uid]["identity_kind"] == "supabase"

    def test_transition_supabase_then_anonymous_stays_supabase(self):
        """Supabase must never be downgraded to anonymous."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc.get_or_create_user(uid, identity_kind="anonymous")
        assert svc._users[uid]["identity_kind"] == "supabase"

    def test_unknown_never_overwrites_anything(self):
        """unknown (default) is the lowest rank, overwrites nothing."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc.get_or_create_user(uid, identity_kind="unknown")
        assert svc._users[uid]["identity_kind"] == "supabase"


# ---------------------------------------------------------------------------
# Supabase backend (SupabaseService) -- FakeClient pattern (R13)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """Minimal in-memory table mock for SupabaseService tests."""

    def __init__(self):
        self._rows = {}  # user_id -> row dict
        self._pending_op = None
        self._filter_uid = None
        self._update_payload = None

    def table(self, name):
        return self

    def select(self, cols):
        self._pending_op = "select"
        return self

    def eq(self, col, val):
        self._filter_uid = val
        return self

    def execute(self):
        if self._pending_op == "select":
            row = self._rows.get(self._filter_uid)
            self._pending_op = None
            return FakeResponse([row] if row else [])
        elif self._pending_op == "insert":
            self._rows[self._insert_data["user_id"]] = dict(self._insert_data)
            self._pending_op = None
            return FakeResponse([self._insert_data])
        elif self._pending_op == "update":
            if self._filter_uid in self._rows:
                self._rows[self._filter_uid].update(self._update_payload)
            self._pending_op = None
            return FakeResponse([self._rows.get(self._filter_uid)])
        return FakeResponse([])

    def insert(self, data):
        self._pending_op = "insert"
        self._insert_data = data
        return self

    def update(self, data):
        self._pending_op = "update"
        self._update_payload = data
        return self


class TestUpgradeOnSightSupabase:
    """Upgrade-on-sight in SupabaseService (R13: proves Postgres path)."""

    def _make_svc(self):
        import os
        import importlib
        os.environ["TB_SUPABASE_URL"] = "https://fake.supabase.co"
        os.environ["TB_SUPABASE_KEY"] = "fake-key"
        try:
            import services.supabase_service as ss_mod
            importlib.reload(ss_mod)
            svc = ss_mod.SupabaseService.__new__(ss_mod.SupabaseService)
            svc._client = FakeTable()
            return svc
        finally:
            os.environ.pop("TB_SUPABASE_URL", None)
            os.environ.pop("TB_SUPABASE_KEY", None)

    def _stored_kind(self, svc, uid):
        return svc._client._rows[uid]["identity_kind"]

    def test_ordering_independence_bare_then_anonymous(self):
        """Row created bare, then anonymous call upgrades it."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)  # creates as 'unknown'
        assert self._stored_kind(svc, uid) == "unknown"
        svc.get_or_create_user(uid, identity_kind="anonymous")
        assert self._stored_kind(svc, uid) == "anonymous"

    def test_ordering_independence_bare_then_supabase(self):
        """Row created bare, then supabase call upgrades it."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid)
        svc.get_or_create_user(uid, identity_kind="supabase")
        assert self._stored_kind(svc, uid) == "supabase"

    def test_monotonicity_known_then_bare(self):
        """Once anonymous is stored, bare call does not overwrite."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="anonymous")
        svc.get_or_create_user(uid)
        assert self._stored_kind(svc, uid) == "anonymous"

    def test_monotonicity_supabase_then_bare(self):
        """Once supabase is stored, bare call does not overwrite."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc.get_or_create_user(uid)
        assert self._stored_kind(svc, uid) == "supabase"

    def test_transition_anonymous_to_supabase(self):
        """Anonymous then supabase -> ends supabase."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="anonymous")
        svc.get_or_create_user(uid, identity_kind="supabase")
        assert self._stored_kind(svc, uid) == "supabase"

    def test_transition_supabase_then_anonymous_stays_supabase(self):
        """Supabase never downgrades to anonymous."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc.get_or_create_user(uid, identity_kind="anonymous")
        assert self._stored_kind(svc, uid) == "supabase"

    def test_unknown_never_overwrites_anything(self):
        """unknown is lowest rank, never overwrites."""
        svc = self._make_svc()
        uid = _fresh_uid()
        svc.get_or_create_user(uid, identity_kind="supabase")
        svc.get_or_create_user(uid, identity_kind="unknown")
        assert self._stored_kind(svc, uid) == "supabase"
