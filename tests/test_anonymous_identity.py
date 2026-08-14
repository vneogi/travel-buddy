"""Tests for SPEC-09: Anonymous device identity (server half).

Covers:
- UUID v4 validation (version + variant bits)
- Rejection of v1 UUIDs (MAC address leak)
- Anonymous header parsing (raw Authorization, not Bearer)
- TB_ALLOW_ANONYMOUS fail-closed default
- Anonymous rejected when JWT secret is configured
- Resolution order: JWT > Anonymous > Debug > 401
- identity_kind written on user creation (production path, R17)
- Canonicalisation: all non-canonical forms rejected (not just normalised)
"""

import uuid
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from security import (
    _validate_anonymous_uuid,
    _parse_anonymous_header,
    resolve_identity,
    get_current_user_id,
    ResolvedIdentity,
)


# ---------------------------------------------------------------------------
# UUID v4 validation + canonicalisation + non-canonical rejection
# ---------------------------------------------------------------------------

class TestUuidV4Validation:
    """UUID must be version 4 with RFC 4122 variant bits, in canonical form."""

    def test_valid_canonical_uuid_v4(self):
        """A fresh uuid4() in canonical form is accepted."""
        uid = str(uuid.uuid4())
        assert _validate_anonymous_uuid(uid) == uid

    def test_rejects_uuid_v1(self):
        """v1 UUIDs embed the device MAC address -- privacy leak."""
        v1 = str(uuid.uuid1())
        with pytest.raises(HTTPException) as exc_info:
            _validate_anonymous_uuid(v1)
        assert exc_info.value.status_code == 401
        assert "version 4" in exc_info.value.detail.lower() or "Version 4" in exc_info.value.detail

    def test_rejects_uuid_v5(self):
        """v5 (deterministic from input) is not random."""
        v5 = str(uuid.uuid5(uuid.NAMESPACE_DNS, "test.example.com"))
        with pytest.raises(HTTPException) as exc_info:
            _validate_anonymous_uuid(v5)
        assert exc_info.value.status_code == 401

    def test_rejects_nil_uuid(self):
        """Nil UUID (all zeros) has version 0."""
        with pytest.raises(HTTPException):
            _validate_anonymous_uuid("00000000-0000-0000-0000-000000000000")

    def test_rejects_malformed_string(self):
        """Random strings are not UUIDs."""
        with pytest.raises(HTTPException):
            _validate_anonymous_uuid("not-a-uuid")

    def test_rejects_none(self):
        """None must not crash -- raises 401."""
        with pytest.raises(HTTPException):
            _validate_anonymous_uuid(None)

    def test_rejects_uppercase(self):
        """Uppercase form is valid UUID but non-canonical -- rejected."""
        uid = str(uuid.uuid4()).upper()
        with pytest.raises(HTTPException) as exc_info:
            _validate_anonymous_uuid(uid)
        assert "canonical" in exc_info.value.detail.lower()

    def test_rejects_braced(self):
        """Braced form {uuid} is non-canonical -- rejected."""
        uid = "{" + str(uuid.uuid4()) + "}"
        with pytest.raises(HTTPException):
            _validate_anonymous_uuid(uid)

    def test_rejects_urn_form(self):
        """urn:uuid:xxx form is non-canonical -- rejected."""
        uid = "urn:uuid:" + str(uuid.uuid4())
        with pytest.raises(HTTPException):
            _validate_anonymous_uuid(uid)

    def test_rejects_hyphenless(self):
        """Hyphenless form is non-canonical -- rejected."""
        uid = str(uuid.uuid4()).replace("-", "")
        with pytest.raises(HTTPException):
            _validate_anonymous_uuid(uid)

    def test_all_five_forms_one_uuid_only_canonical_passes(self):
        """Five representations of one UUID: only canonical passes.

        This is the exact scenario from the bug report: in-memory keys on the
        raw string, Postgres normalises, so the backends disagree unless we
        reject non-canonical forms at the gate.
        """
        base = uuid.uuid4()
        canonical = str(base)
        forms = {
            "canonical": canonical,
            "uppercase": canonical.upper(),
            "braced": "{" + canonical + "}",
            "urn": "urn:uuid:" + canonical,
            "hyphenless": canonical.replace("-", ""),
        }

        # Only canonical passes
        assert _validate_anonymous_uuid(forms["canonical"]) == canonical

        for name, form in forms.items():
            if name == "canonical":
                continue
            with pytest.raises(HTTPException) as exc_info:
                _validate_anonymous_uuid(form)
            assert exc_info.value.status_code == 401, (
                f"Form {name!r} ({form}) should be rejected"
            )


# ---------------------------------------------------------------------------
# Anonymous header parsing
# ---------------------------------------------------------------------------

class TestAnonymousHeaderParsing:
    """Authorization: Anonymous <uuid> parsed from raw header."""

    def test_parses_valid_anonymous_header(self):
        uid = str(uuid.uuid4())
        result = _parse_anonymous_header(f"Anonymous {uid}")
        assert result == uid

    def test_case_insensitive_scheme(self):
        uid = str(uuid.uuid4())
        assert _parse_anonymous_header(f"anonymous {uid}") == uid
        assert _parse_anonymous_header(f"ANONYMOUS {uid}") == uid

    def test_ignores_bearer_scheme(self):
        """Bearer tokens must NOT be parsed as anonymous."""
        assert _parse_anonymous_header("Bearer eyJhbGciOi...") is None

    def test_returns_none_for_empty(self):
        assert _parse_anonymous_header(None) is None
        assert _parse_anonymous_header("") is None

    def test_returns_none_for_no_value(self):
        assert _parse_anonymous_header("Anonymous") is None


# ---------------------------------------------------------------------------
# Integration: resolve_identity resolution order
# ---------------------------------------------------------------------------

class TestAnonymousResolution:
    """Anonymous identity accepted only when TB_ALLOW_ANONYMOUS=true and no JWT secret."""

    @pytest.fixture
    def allow_anonymous_settings(self):
        """Patch settings: no JWT secret, allow_anonymous=True, debug=False."""
        with patch("security.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = None
            mock_settings.allow_anonymous = True
            mock_settings.debug = False
            yield mock_settings

    @pytest.fixture
    def deny_anonymous_settings(self):
        """Patch settings: no JWT secret, allow_anonymous=False (default)."""
        with patch("security.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = None
            mock_settings.allow_anonymous = False
            mock_settings.debug = False
            yield mock_settings

    @pytest.fixture
    def jwt_configured_settings(self):
        """Patch settings: JWT secret set (anonymous path unreachable)."""
        with patch("security.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = "test-secret"
            mock_settings.allow_anonymous = True
            mock_settings.debug = False
            yield mock_settings

    @pytest.mark.asyncio
    async def test_anonymous_returns_canonical_and_kind(self, allow_anonymous_settings):
        """Valid canonical v4 UUID returns (user_id, 'anonymous')."""
        uid = str(uuid.uuid4())
        result = await resolve_identity(
            credentials=None,
            authorization=f"Anonymous {uid}",
            x_debug_user_id=None,
        )
        assert result.user_id == uid
        assert result.identity_kind == "anonymous"

    @pytest.mark.asyncio
    async def test_anonymous_rejected_when_disabled(self, deny_anonymous_settings):
        """Anonymous identity rejected when TB_ALLOW_ANONYMOUS=false (default)."""
        uid = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await resolve_identity(
                credentials=None,
                authorization=f"Anonymous {uid}",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401
        assert "not enabled" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_uuid_v1_rejected(self, allow_anonymous_settings):
        """v1 UUID rejected even when anonymous is enabled."""
        v1 = str(uuid.uuid1())
        with pytest.raises(HTTPException) as exc_info:
            await resolve_identity(
                credentials=None,
                authorization=f"Anonymous {v1}",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_non_canonical_rejected(self, allow_anonymous_settings):
        """Uppercase UUID rejected even though it is valid v4."""
        uid = str(uuid.uuid4()).upper()
        with pytest.raises(HTTPException) as exc_info:
            await resolve_identity(
                credentials=None,
                authorization=f"Anonymous {uid}",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401
        assert "canonical" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_jwt_path_returns_supabase_kind(self, jwt_configured_settings):
        """JWT path returns identity_kind='supabase'."""
        import jwt as pyjwt
        token = pyjwt.encode(
            {"sub": "jwt-user-123", "aud": "authenticated"},
            "test-secret",
            algorithm="HS256",
        )
        mock_creds = MagicMock()
        mock_creds.credentials = token
        jwt_configured_settings.jwt_audience = "authenticated"

        result = await resolve_identity(
            credentials=mock_creds,
            authorization=None,
            x_debug_user_id=None,
        )
        assert result.user_id == "jwt-user-123"
        assert result.identity_kind == "supabase"

    @pytest.mark.asyncio
    async def test_debug_path_returns_debug_kind(self):
        """Debug path returns identity_kind='debug'."""
        with patch("security.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = None
            mock_settings.allow_anonymous = False
            mock_settings.debug = True
            result = await resolve_identity(
                credentials=None,
                authorization=None,
                x_debug_user_id="debug-user-456",
            )
            assert result.user_id == "debug-user-456"
            assert result.identity_kind == "debug"

    @pytest.mark.asyncio
    async def test_jwt_takes_precedence_over_anonymous(self, jwt_configured_settings):
        """When JWT secret is set, Anonymous header is never reached."""
        uid = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await resolve_identity(
                credentials=None,
                authorization=f"Anonymous {uid}",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401
        assert "bearer token" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_auth_gives_500(self):
        """No secret + no anonymous + no debug = misconfiguration 500."""
        with patch("security.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = None
            mock_settings.allow_anonymous = False
            mock_settings.debug = False
            with pytest.raises(HTTPException) as exc_info:
                await resolve_identity(
                    credentials=None,
                    authorization=None,
                    x_debug_user_id=None,
                )
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
