"""Travel Buddy -- Authentication & Authorization.

Resolution order (SPEC-43 Gap 1, supersedes the SPEC-09 device-UUID path):

1. ``Authorization: Anonymous <anything>`` -> 401 in EVERY configuration.
   A client-chosen UUID is never a credential. ``TB_ALLOW_ANONYMOUS`` is a
   retained no-op setting.
2. ``TB_SUPABASE_JWKS_URL`` set -> Bearer token verified against the
   project's JWKS: key by ``kid`` (server-fetched, cached, refetched on an
   unknown ``kid`` so rotation never needs an APK), algorithm from the JWK
   (asymmetric only), ``iss`` == ``TB_SUPABASE_JWT_ISS``, ``aud`` includes
   ``jwt_audience``, ``exp`` in the future, non-empty ``sub`` (= user_id),
   ``role == authenticated``; ``is_anonymous`` optional but boolean.
   Supabase anonymous sign-ins satisfy this. The HS256 secret is NOT used.
3. Else ``TB_SUPABASE_JWT_SECRET`` set -> legacy HS256 verification.
4. Else ``TB_DEBUG=true`` -> ``X-Debug-User-Id`` (in-memory pytest path).
   Debug never wins over JWKS or the JWT secret.
5. Otherwise 500 (server auth misconfiguration).

identity_kind is resolved here and passed through to get_or_create_user so the
database records HOW a user was identified. Values: 'supabase', 'debug'
('anonymous' rows from SPEC-09 remain readable but are no longer issued).
Tokens are never logged.
"""

import inspect
from typing import Any, Dict, NamedTuple, Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings
from models.schemas import TripState

# auto_error=False lets us return clearer 401s and run the dev fallback below.
_bearer = HTTPBearer(auto_error=False)

ALLOWED_ROLES = frozenset({"authenticated"})
_ASYMMETRIC_ALGS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)
JWKS_CACHE_SECONDS = 600
# Unknown-kid refetch cooldown (PyJWT >= 2.13). Bounds JWKS fetches caused by
# junk kids; a genuinely rotated key is picked up within this window.
JWKS_REFRESH_COOLDOWN_SECONDS = 30

_jwks_clients: Dict[str, "jwt.PyJWKClient"] = {}


class ResolvedIdentity(NamedTuple):
    """The result of identity resolution: who, and how they were identified."""

    user_id: str
    identity_kind: str  # 'supabase' | 'debug'


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _is_anonymous_scheme(authorization: Optional[str]) -> bool:
    if not authorization:
        return False
    return authorization.split(None, 1)[0].lower() == "anonymous"


def get_jwks_client(url: str) -> "jwt.PyJWKClient":
    """Process-wide JWKS client per URL (keys cached, refetch on unknown kid)."""
    client = _jwks_clients.get(url)
    if client is None:
        kwargs: Dict[str, Any] = {
            "cache_keys": True,
            "cache_jwk_set": True,
            "lifespan": JWKS_CACHE_SECONDS,
            "timeout": 5,
        }
        if "cooldown_duration" in inspect.signature(jwt.PyJWKClient.__init__).parameters:
            kwargs["cooldown_duration"] = JWKS_REFRESH_COOLDOWN_SECONDS
        client = jwt.PyJWKClient(url, **kwargs)
        _jwks_clients[url] = client
    return client


def reset_jwks_cache() -> None:
    _jwks_clients.clear()


def _check_claims(payload: Dict[str, Any]) -> str:
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.strip():
        raise _unauthorized("Token missing 'sub' claim")
    if payload.get("role") not in ALLOWED_ROLES:
        raise _unauthorized("Token role is not allowed")
    if "is_anonymous" in payload and not isinstance(payload["is_anonymous"], bool):
        raise _unauthorized("Token 'is_anonymous' claim is malformed")
    return user_id


def _decode_jwks_jwt(token: str) -> str:
    """Verify a Supabase access token from JWKS and return ``sub``."""
    if not settings.supabase_jwt_iss:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth misconfiguration: TB_SUPABASE_JWT_ISS is not set",
        )
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid access token: malformed header")
    if not header.get("kid"):
        raise _unauthorized("Invalid access token: missing 'kid'")
    try:
        signing_key = get_jwks_client(settings.supabase_jwks_url).get_signing_key(header["kid"])
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch signing keys",
        )
    except (jwt.PyJWKClientError, jwt.InvalidKeyError):
        raise _unauthorized("Invalid access token: unknown signing key")

    alg = getattr(signing_key, "algorithm_name", None)
    if alg not in _ASYMMETRIC_ALGS or header.get("alg") != alg:
        raise _unauthorized("Invalid access token: algorithm not allowed")
    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[alg],
            audience=settings.jwt_audience,
            issuer=settings.supabase_jwt_iss,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Access token has expired")
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"Invalid access token: {type(exc).__name__}")
    return _check_claims(payload)


def _decode_supabase_jwt(token: str) -> str:
    """Legacy HS256 verification (only when JWKS URL is unset)."""
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Access token has expired")
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"Invalid access token: {exc}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    return user_id


def _require_bearer(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")
    return credentials.credentials


async def resolve_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    authorization: Optional[str] = Header(default=None),
    x_debug_user_id: Optional[str] = Header(default=None),
) -> ResolvedIdentity:
    """Core identity resolution. Returns (user_id, identity_kind).

    This is the single source of truth for HOW a user was identified.
    Routers that need to pass identity_kind to get_or_create_user should
    depend on this directly.
    """
    # --- Retired SPEC-09 scheme: a client-chosen UUID is never a credential ---
    if _is_anonymous_scheme(authorization):
        raise _unauthorized(
            "Anonymous device identity is no longer accepted. Sign in to get an access token."
        )

    # --- Path 1: JWKS (asymmetric, rotatable) ---
    if settings.supabase_jwks_url:
        user_id = _decode_jwks_jwt(_require_bearer(credentials))
        return ResolvedIdentity(user_id=user_id, identity_kind="supabase")

    # --- Path 2: legacy HS256 secret ---
    if settings.supabase_jwt_secret:
        user_id = _decode_supabase_jwt(_require_bearer(credentials))
        return ResolvedIdentity(user_id=user_id, identity_kind="supabase")

    # --- Path 3: Debug fallback (in-memory pytest / local dev only) ---
    if settings.debug:
        if not x_debug_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Auth not configured. In debug mode, pass an 'X-Debug-User-Id' "
                    "header, or set TB_SUPABASE_JWKS_URL to enable real auth."
                ),
            )
        return ResolvedIdentity(user_id=x_debug_user_id, identity_kind="debug")

    # --- Path 4: Misconfigured production ---
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server auth misconfiguration: TB_SUPABASE_JWKS_URL is not set",
    )


async def get_current_user_id(
    identity: ResolvedIdentity = Depends(resolve_identity),
) -> str:
    """Backward-compat dependency returning just the user_id string.

    Routers that only need user_id (and do not call get_or_create_user)
    can still depend on this.
    """
    return identity.user_id


def require_trip_owner(trip: Optional[TripState], user_id: str) -> TripState:
    """Return the trip if it exists and belongs to user_id; else raise.

    404 for missing trips, 403 for trips owned by someone else.
    """
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )
    if trip.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this trip",
        )
    return trip
