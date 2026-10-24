"""SPEC-43 Gap 1 -- server-issued anonymous JWT verified from JWKS.

In-process RSA keypairs + a stubbed JWKS fetch. No live Supabase Auth call.

R17 sabotage: re-accept ``Authorization: Anonymous <uuid>`` as user_id in
``resolve_identity`` while JWKS is configured ->
``test_anonymous_uuid_cannot_read_or_mutate_trip`` fails.
"""

import time
import uuid
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import security
from tests.conftest import auth

ISS = "https://projref.supabase.co/auth/v1"
JWKS_URL = "https://projref.supabase.co/auth/v1/.well-known/jwks.json"


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


K1 = _keypair()
K2 = _keypair()
OTHER = _keypair()


def _jwk(key, kid):
    d = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    d.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return d


def make_token(*, key=K1, kid="k1", alg="RS256", drop=(), **over):
    now = int(time.time())
    claims = {
        "sub": over.pop("sub", str(uuid.uuid4())),
        "iss": ISS,
        "aud": "authenticated",
        "role": "authenticated",
        "is_anonymous": True,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(over)
    for k in drop:
        claims.pop(k, None)
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid} if kid else None)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def jwks(monkeypatch):
    """Configure JWKS mode with a stub key set; yields mutable state."""
    state = {"keys": [_jwk(K1, "k1")], "fetches": 0}

    def fake_fetch(self):
        state["fetches"] += 1
        return {"keys": list(state["keys"])}

    security.reset_jwks_cache()
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fake_fetch)
    monkeypatch.setattr(security.settings, "supabase_jwks_url", JWKS_URL)
    monkeypatch.setattr(security.settings, "supabase_jwt_iss", ISS)
    monkeypatch.setattr(security.settings, "jwt_audience", "authenticated")
    monkeypatch.setattr(security.settings, "allow_anonymous", True)  # must be a no-op
    yield state
    security.reset_jwks_cache()


@pytest.fixture
def no_llm():
    with patch("services.llm_service.llm_service.complete", new_callable=AsyncMock) as llm:
        yield llm
    llm.assert_not_called()


def _create_trip(client, headers):
    r = client.post(
        "/api/v1/trip/create", headers=headers, json={"start_date": "2026-08-05T09:00:00"}
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


class TestAnonymousCredentialKilled:
    def test_anonymous_uuid_cannot_read_or_mutate_trip(self, client, jwks, no_llm):
        """R17 target. Even the owner's own UUID in the retired scheme is refused."""
        owner = str(uuid.uuid4())
        trip_id = _create_trip(client, bearer(make_token(sub=owner)))
        anon = {"Authorization": f"Anonymous {owner}"}

        assert client.get(f"/api/v1/trip/{trip_id}", headers=anon).status_code == 401
        r = client.post(
            "/api/v1/trip/event",
            headers=anon,
            json={"trip_id": trip_id, "event_type": "reroute", "message": "x"},
        )
        assert r.status_code == 401
        assert client.get("/api/v1/user/status", headers=anon).status_code == 401
        # The owner's real token still works.
        ok = client.get(f"/api/v1/trip/{trip_id}", headers=bearer(make_token(sub=owner)))
        assert ok.status_code == 200

    def test_anonymous_uuid_rejected_in_debug_mode_too(self, client, monkeypatch):
        import security as sec

        monkeypatch.setattr(sec.settings, "allow_anonymous", True)
        uid = str(uuid.uuid4())
        r = client.get(
            "/api/v1/user/status",
            headers={"Authorization": f"Anonymous {uid}", "X-Debug-User-Id": uid},
        )
        assert r.status_code == 401


class TestJwksVerification:
    def test_valid_token_user_status_is_sub(self, client, jwks, no_llm):
        sub = str(uuid.uuid4())
        r = client.get("/api/v1/user/status", headers=bearer(make_token(sub=sub)))
        assert r.status_code == 200, r.text
        assert r.json()["user_id"] == sub

    def test_is_anonymous_absent_or_false_accepted(self, client, jwks):
        for tok in (make_token(drop=("is_anonymous",)), make_token(is_anonymous=False)):
            assert client.get("/api/v1/user/status", headers=bearer(tok)).status_code == 200

    @pytest.mark.parametrize(
        "token_kw",
        [
            {"exp": int(time.time()) - 10},
            {"iss": "https://otherproj.supabase.co/auth/v1"},
            {"aud": "someone-else"},
            {"drop": ("sub",)},
            {"sub": ""},
            {"drop": ("exp",)},
            {"role": "anon"},
            {"role": "service_role"},
            {"drop": ("role",)},
            {"is_anonymous": "yes"},
            {"key": OTHER},  # right kid, wrong signature
            {"kid": "unknown"},
            {"kid": None},
        ],
        ids=[
            "expired",
            "wrong_iss",
            "wrong_aud",
            "no_sub",
            "empty_sub",
            "no_exp",
            "role_anon",
            "role_service",
            "no_role",
            "bad_is_anonymous",
            "bad_signature",
            "unknown_kid",
            "no_kid",
        ],
    )
    def test_invalid_tokens_401(self, client, jwks, token_kw):
        r = client.get("/api/v1/user/status", headers=bearer(make_token(**token_kw)))
        assert r.status_code == 401, r.text

    def test_hs256_secret_not_used_when_jwks_set(self, client, jwks, monkeypatch):
        secret = "legacy-hs256-secret-value-32-bytes!"
        monkeypatch.setattr(security.settings, "supabase_jwt_secret", secret)
        tok = make_token(key=secret, alg="HS256", kid="k1")
        assert client.get("/api/v1/user/status", headers=bearer(tok)).status_code == 401

    def test_alg_none_rejected(self, client, jwks):
        tok = make_token(key=None, alg="none")
        assert client.get("/api/v1/user/status", headers=bearer(tok)).status_code == 401

    def test_debug_header_ignored_when_jwks_configured(self, client, jwks):
        r = client.get("/api/v1/user/status", headers={"X-Debug-User-Id": "attacker"})
        assert r.status_code == 401

    def test_missing_bearer_401(self, client, jwks):
        assert client.get("/api/v1/user/status").status_code == 401

    def test_rotation_refetches_without_restart(self, client, jwks, monkeypatch):
        monkeypatch.setattr(security, "JWKS_REFRESH_COOLDOWN_SECONDS", 0)
        security.reset_jwks_cache()
        assert client.get("/api/v1/user/status", headers=bearer(make_token())).status_code == 200
        before = jwks["fetches"]
        tok2 = make_token(key=K2, kid="k2")
        assert client.get("/api/v1/user/status", headers=bearer(tok2)).status_code == 401
        jwks["keys"] = [_jwk(K1, "k1"), _jwk(K2, "k2")]  # project rotates keys
        assert client.get("/api/v1/user/status", headers=bearer(tok2)).status_code == 200
        assert jwks["fetches"] > before

    def test_unknown_kid_flood_does_not_refetch_each_time(self, client, jwks):
        assert client.get("/api/v1/user/status", headers=bearer(make_token())).status_code == 200
        for i in range(5):
            tok = make_token(kid=f"junk-{i}")
            assert client.get("/api/v1/user/status", headers=bearer(tok)).status_code == 401
        assert jwks["fetches"] <= 2

    def test_keys_cached_between_requests(self, client, jwks):
        tok = make_token()
        for _ in range(3):
            assert client.get("/api/v1/user/status", headers=bearer(tok)).status_code == 200
        assert jwks["fetches"] == 1

    def test_jwks_without_issuer_is_misconfiguration(self, client, jwks, monkeypatch):
        monkeypatch.setattr(security.settings, "supabase_jwt_iss", None)
        r = client.get("/api/v1/user/status", headers=bearer(make_token()))
        assert r.status_code == 500

    def test_two_jwt_users_cannot_read_each_others_trip(self, client, jwks, no_llm):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        trip_id = _create_trip(client, bearer(make_token(sub=a)))
        assert (
            client.get(f"/api/v1/trip/{trip_id}", headers=bearer(make_token(sub=b))).status_code
            == 403
        )

    def test_error_detail_never_echoes_token(self, client, jwks):
        tok = make_token(iss="https://otherproj.supabase.co/auth/v1")
        r = client.get("/api/v1/user/status", headers=bearer(tok))
        assert tok not in r.text


class TestDebugPathUnchanged:
    def test_debug_header_works_when_jwks_and_secret_unset(self, client):
        assert not security.settings.supabase_jwks_url
        assert not security.settings.supabase_jwt_secret
        r = client.get("/api/v1/user/status", headers=auth("dbg-user"))
        assert r.status_code == 200 and r.json()["user_id"] == "dbg-user"

    def test_two_debug_users_ownership(self, client, no_llm):
        trip_id = _create_trip(client, auth("g1-u1"))
        assert client.get(f"/api/v1/trip/{trip_id}", headers=auth("g1-u1")).status_code == 200
        assert client.get(f"/api/v1/trip/{trip_id}", headers=auth("g1-u2")).status_code == 403
