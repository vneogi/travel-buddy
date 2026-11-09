"""SPEC-43 Gap 4 slice 8: process-local erase denylist and resolve_identity.

The JWKS keypair and stub fetch are copied (minimal) from
tests/test_spec43_g1_anon_jwt.py. No live Supabase, no network.
"""

import ast
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import security
from services import data_rights_token_deny as deny_module
from services.data_rights_token_deny import (
    DENY_TTL_SECONDS,
    deny_identity,
    is_denied,
    reset_denylist,
)

USER_A = "8f0d2b6c-4a1e-4c3a-9b7e-0000000000a1"
USER_B = "8f0d2b6c-4a1e-4c3a-9b7e-0000000000b2"
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

ISS = "https://projref.supabase.co/auth/v1"
JWKS_URL = "https://projref.supabase.co/auth/v1/.well-known/jwks.json"
K1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(key, kid):
    d = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    d.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return d


def make_token(*, sub):
    now = int(time.time())
    claims = {
        "sub": sub,
        "iss": ISS,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(claims, K1, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def jwks(monkeypatch):
    security.reset_jwks_cache()
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [_jwk(K1, "k1")]})
    monkeypatch.setattr(security.settings, "supabase_jwks_url", JWKS_URL)
    monkeypatch.setattr(security.settings, "supabase_jwt_iss", ISS)
    monkeypatch.setattr(security.settings, "jwt_audience", "authenticated")
    yield
    security.reset_jwks_cache()


@pytest.fixture(autouse=True)
def _clean():
    reset_denylist()
    yield
    reset_denylist()


def _resolve(*, token=None, debug_user=None):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token) if token else None
    return asyncio.run(
        security.resolve_identity(
            credentials=creds,
            authorization=f"Bearer {token}" if token else None,
            x_debug_user_id=debug_user,
        )
    )


# --- unit ------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", "   ", 42, b"abc"])
def test_deny_identity_rejects_blank_before_store(bad):
    with pytest.raises(ValueError):
        deny_identity(bad)
    assert deny_module._denied == {}


def test_is_denied_true_until_ttl_then_false():
    assert DENY_TTL_SECONDS == 3600
    until = deny_identity(USER_A, now=T0)
    assert until == T0 + timedelta(seconds=DENY_TTL_SECONDS)
    assert is_denied(USER_A, now=T0)
    assert is_denied(USER_A, now=until - timedelta(seconds=1))
    assert not is_denied(USER_A, now=until)
    # Expired entries are dropped on read.
    assert USER_A not in deny_module._denied
    assert not is_denied(USER_B, now=T0)


def test_re_deny_extends_until():
    first = deny_identity(USER_A, now=T0)
    later = T0 + timedelta(minutes=50)
    second = deny_identity(USER_A, now=later)
    assert second == later + timedelta(seconds=DENY_TTL_SECONDS)
    assert second > first
    assert is_denied(USER_A, now=first + timedelta(minutes=5))
    # An older re-deny never shortens the window.
    assert deny_identity(USER_A, now=T0) == second


@pytest.mark.parametrize("bad", [None, "", "   ", 42, b"abc", object()])
def test_is_denied_blank_is_false(bad):
    deny_identity(USER_A)
    assert is_denied(bad) is False


def test_reset_denylist_clears_all():
    deny_identity(USER_A)
    deny_identity(USER_B)
    assert is_denied(USER_A) and is_denied(USER_B)
    reset_denylist()
    assert not is_denied(USER_A) and not is_denied(USER_B)
    assert deny_module._denied == {}


def test_deny_module_has_no_supabase_import():
    source = Path(deny_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= {"__future__", "threading", "datetime", "typing"}, roots
    assert "print(" not in source and "import logging" not in source


# --- security --------------------------------------------------------------


def test_resolve_identity_jwks_refuses_denied_user(jwks):
    token_a, token_b = make_token(sub=USER_A), make_token(sub=USER_B)
    assert _resolve(token=token_a).user_id == USER_A
    deny_identity(USER_A)
    with pytest.raises(HTTPException) as excinfo:
        _resolve(token=token_a)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Access token has been revoked"
    assert USER_A not in str(excinfo.value.detail)
    ok = _resolve(token=token_b)
    assert (ok.user_id, ok.identity_kind) == (USER_B, "supabase")


def test_resolve_identity_hs256_refuses_denied_user(monkeypatch):
    secret = "g4-deny-test-secret-0123456789abcdef"
    monkeypatch.setattr(security.settings, "supabase_jwks_url", "")
    monkeypatch.setattr(security.settings, "supabase_jwt_secret", secret)
    monkeypatch.setattr(security.settings, "supabase_jwt_iss", None)
    now = int(time.time())
    base = {"aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + 600}
    token = jwt.encode(dict(base, sub=USER_A), secret, algorithm="HS256")
    assert _resolve(token=token).user_id == USER_A
    deny_identity(USER_A)
    with pytest.raises(HTTPException) as excinfo:
        _resolve(token=token)
    assert excinfo.value.status_code == 401


def test_resolve_identity_debug_refuses_denied_user():
    assert security.settings.debug
    deny_identity(USER_A)
    with pytest.raises(HTTPException) as excinfo:
        _resolve(debug_user=USER_A)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Access token has been revoked"
    ok = _resolve(debug_user=USER_B)
    assert (ok.user_id, ok.identity_kind) == (USER_B, "debug")


def test_resolve_identity_allows_after_ttl(monkeypatch):
    deny_identity(USER_A, now=datetime.now(timezone.utc) - timedelta(seconds=DENY_TTL_SECONDS))
    assert _resolve(debug_user=USER_A).user_id == USER_A
