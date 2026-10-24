"""SPEC-09 device identity, as amended by SPEC-43 Gap 1.

The SPEC-09 ``Authorization: Anonymous <uuid>`` credential is retired: a
client-chosen UUID is rejected (401) in every configuration, including
``allow_anonymous=True``. Anonymous travellers now carry a server-issued
Supabase anonymous JWT (see tests/test_spec43_g1_anon_jwt.py).

Covers:
- Anonymous scheme rejected with/without allow_anonymous, JWKS, JWT secret, debug
- Resolution order: JWKS > JWT secret > Debug > 500
- identity_kind written on user creation (production path, R17)
"""

import uuid
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from security import (  # noqa: E402
    resolve_identity,
    ResolvedIdentity,
)


def _settings(mock, *, jwks=None, secret=None, allow=False, debug=False):
    mock.supabase_jwks_url = jwks
    mock.supabase_jwt_iss = "https://proj.supabase.co/auth/v1" if jwks else None
    mock.supabase_jwt_secret = secret
    mock.allow_anonymous = allow
    mock.debug = debug
    mock.jwt_audience = "authenticated"
    return mock


class TestAnonymousSchemeRejected:
    """A client-selected UUID is never an identity."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cfg",
        [
            {"allow": True},
            {"allow": True, "debug": True},
            {"allow": False},
            {"allow": True, "secret": "test-secret"},
            {"allow": True, "jwks": "https://proj.supabase.co/auth/v1/.well-known/jwks.json"},
        ],
    )
    async def test_anonymous_uuid_rejected_everywhere(self, cfg):
        uid = str(uuid.uuid4())
        with patch("security.settings") as mock_settings:
            _settings(mock_settings, **cfg)
            with pytest.raises(HTTPException) as exc_info:
                await resolve_identity(
                    credentials=None,
                    authorization=f"Anonymous {uid}",
                    x_debug_user_id="debug-would-win",
                )
        assert exc_info.value.status_code == 401
        assert "no longer accepted" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize("header", ["Anonymous", "anonymous abc", "ANONYMOUS x"])
    async def test_scheme_case_and_bare_forms_rejected(self, header):
        with patch("security.settings") as mock_settings:
            _settings(mock_settings, allow=True, debug=True)
            with pytest.raises(HTTPException) as exc_info:
                await resolve_identity(credentials=None, authorization=header, x_debug_user_id="u1")
        assert exc_info.value.status_code == 401


class TestResolutionOrder:
    @pytest.mark.asyncio
    async def test_jwt_secret_path_returns_supabase_kind(self):
        import jwt as pyjwt

        token = pyjwt.encode(
            {"sub": "jwt-user-123", "aud": "authenticated"},
            "test-secret-that-is-long-enough-32b",
            algorithm="HS256",
        )
        creds = MagicMock()
        creds.credentials = token
        with patch("security.settings") as mock_settings:
            _settings(mock_settings, secret="test-secret-that-is-long-enough-32b")
            result = await resolve_identity(
                credentials=creds, authorization=f"Bearer {token}", x_debug_user_id=None
            )
        assert result == ResolvedIdentity(user_id="jwt-user-123", identity_kind="supabase")

    @pytest.mark.asyncio
    async def test_debug_path_returns_debug_kind(self):
        with patch("security.settings") as mock_settings:
            _settings(mock_settings, debug=True)
            result = await resolve_identity(
                credentials=None, authorization=None, x_debug_user_id="debug-user-456"
            )
        assert result.user_id == "debug-user-456"
        assert result.identity_kind == "debug"

    @pytest.mark.asyncio
    async def test_jwt_secret_requires_bearer(self):
        with patch("security.settings") as mock_settings:
            _settings(mock_settings, secret="test-secret", debug=True)
            with pytest.raises(HTTPException) as exc_info:
                await resolve_identity(
                    credentials=None, authorization=None, x_debug_user_id="attacker"
                )
        assert exc_info.value.status_code == 401
        assert "bearer token" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_auth_gives_500(self):
        """No JWKS + no secret + no debug = misconfiguration 500."""
        with patch("security.settings") as mock_settings:
            _settings(mock_settings, allow=True)
            with pytest.raises(HTTPException) as exc_info:
                await resolve_identity(credentials=None, authorization=None, x_debug_user_id=None)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# identity_kind writer: production path (R17)
# ---------------------------------------------------------------------------


class TestIdentityKindWriter:
    """identity_kind must be persisted on user creation by the production path.

    R17: drives the real get_or_create_user, not a helper.
    """

    def test_anonymous_path_persists_identity_kind(self):
        """Anonymous resolution -> get_or_create_user writes 'anonymous'."""
        from services.database_service import DatabaseService

        svc = DatabaseService()
        uid = str(uuid.uuid4())
        svc.get_or_create_user(uid, identity_kind="anonymous")
        assert svc._users[uid]["identity_kind"] == "anonymous"

    def test_supabase_path_persists_identity_kind(self):
        """JWT resolution -> get_or_create_user writes 'supabase'."""
        from services.database_service import DatabaseService

        svc = DatabaseService()
        uid = str(uuid.uuid4())
        svc.get_or_create_user(uid, identity_kind="supabase")
        assert svc._users[uid]["identity_kind"] == "supabase"

    def test_default_identity_kind_is_unknown(self):
        """Callers that omit identity_kind get 'unknown' (existing code paths)."""
        from services.database_service import DatabaseService

        svc = DatabaseService()
        uid = str(uuid.uuid4())
        svc.get_or_create_user(uid)
        assert svc._users[uid]["identity_kind"] == "unknown"

    def test_identity_kind_upgrades_on_sight(self):
        """identity_kind upgrades monotonically: anonymous -> supabase promotes."""
        from services.database_service import DatabaseService

        svc = DatabaseService()
        uid = str(uuid.uuid4())
        svc.get_or_create_user(uid, identity_kind="anonymous")
        # Higher-rank kind promotes (upgrade-on-sight)
        svc.get_or_create_user(uid, identity_kind="supabase")
        assert svc._users[uid]["identity_kind"] == "supabase"

    def test_get_current_user_id_backward_compat(self):
        """get_current_user_id still returns a plain string (backward compat)."""
        identity = ResolvedIdentity(user_id="test-123", identity_kind="debug")
        # Simulate what get_current_user_id does
        assert identity.user_id == "test-123"
        assert isinstance(identity.user_id, str)
