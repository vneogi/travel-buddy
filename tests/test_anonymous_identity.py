"""Tests for SPEC-09: Anonymous device identity (server half).

Covers:
- UUID v4 validation (version + variant bits)
- Rejection of v1 UUIDs (MAC address leak)
- Anonymous header parsing (raw Authorization, not Bearer)
- TB_ALLOW_ANONYMOUS fail-closed default
- Anonymous rejected when JWT secret is configured
- Resolution order: JWT > Anonymous > Debug > 401
"""

import uuid
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from security import _is_valid_uuid_v4, _parse_anonymous_header, get_current_user_id


# ---------------------------------------------------------------------------
# UUID v4 validation
# ---------------------------------------------------------------------------

class TestUuidV4Validation:
    """UUID must be version 4 with RFC 4122 variant bits."""

    def test_valid_uuid_v4(self):
        """A fresh uuid4() is accepted."""
        assert _is_valid_uuid_v4(str(uuid.uuid4())) is True

    def test_rejects_uuid_v1(self):
        """v1 UUIDs embed the device MAC address -- privacy leak."""
        v1 = str(uuid.uuid1())
        assert _is_valid_uuid_v4(v1) is False

    def test_rejects_uuid_v5(self):
        """v5 (deterministic from input) is not random."""
        v5 = str(uuid.uuid5(uuid.NAMESPACE_DNS, "test.example.com"))
        assert _is_valid_uuid_v4(v5) is False

    def test_rejects_nil_uuid(self):
        """Nil UUID (all zeros) has version 0."""
        assert _is_valid_uuid_v4("00000000-0000-0000-0000-000000000000") is False

    def test_rejects_malformed_string(self):
        """Random strings are not UUIDs."""
        assert _is_valid_uuid_v4("not-a-uuid") is False
        assert _is_valid_uuid_v4("") is False
        assert _is_valid_uuid_v4("12345678") is False

    def test_rejects_none(self):
        """None must not crash."""
        assert _is_valid_uuid_v4(None) is False

    def test_rejects_short_hex(self):
        """8-char node IDs (from trip nodes) are not valid UUIDs."""
        assert _is_valid_uuid_v4("a1b2c3d4") is False

    def test_uuid_v4_format_details(self):
        """Version nibble is 4, variant bits are 10xx."""
        v4 = uuid.uuid4()
        assert v4.version == 4
        assert v4.variant == uuid.RFC_4122
        assert _is_valid_uuid_v4(str(v4)) is True


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
# Integration: get_current_user_id resolution order
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
    async def test_valid_anonymous_accepted(self, allow_anonymous_settings):
        """Valid v4 UUID with Anonymous scheme returns the UUID as user_id."""
        uid = str(uuid.uuid4())
        result = await get_current_user_id(
            credentials=None,
            authorization=f"Anonymous {uid}",
            x_debug_user_id=None,
        )
        assert result == uid

    @pytest.mark.asyncio
    async def test_anonymous_rejected_when_disabled(self, deny_anonymous_settings):
        """Anonymous identity rejected when TB_ALLOW_ANONYMOUS=false (default)."""
        uid = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(
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
            await get_current_user_id(
                credentials=None,
                authorization=f"Anonymous {v1}",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401
        assert "version 4" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_malformed_uuid_rejected(self, allow_anonymous_settings):
        """Non-UUID string rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(
                credentials=None,
                authorization="Anonymous not-a-uuid",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_takes_precedence(self, jwt_configured_settings):
        """When JWT secret is set, Anonymous header is never reached -- 401 for missing bearer."""
        uid = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(
                credentials=None,
                authorization=f"Anonymous {uid}",
                x_debug_user_id=None,
            )
        assert exc_info.value.status_code == 401
        assert "bearer token" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_auth_no_anonymous_no_debug_gives_500(self):
        """No secret + no anonymous + no debug = misconfiguration 500."""
        with patch("security.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = None
            mock_settings.allow_anonymous = False
            mock_settings.debug = False
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id(
                    credentials=None,
                    authorization=None,
                    x_debug_user_id=None,
                )
            assert exc_info.value.status_code == 500
