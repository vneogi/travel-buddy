"""Travel Buddy -- Authentication & Authorization.

Resolution order (SPEC-09):
1. Real Supabase JWT (when TB_SUPABASE_JWT_SECRET set) -- verified user
2. Authorization: Anonymous <uuid-v4> -- device identity (when TB_ALLOW_ANONYMOUS=true
   AND no JWT secret configured). UUID must be version 4 with correct variant bits,
   in canonical form (lowercase hyphenated). Anything else is rejected.
3. X-Debug-User-Id -- only when no JWT secret AND TB_DEBUG=true
4. Otherwise 401

TB_ALLOW_ANONYMOUS defaults to False (fail-closed). Deployments that accept
anonymous device identities must opt in explicitly.

identity_kind is resolved here and passed through to get_or_create_user so the
database records HOW a user was identified. Values: 'supabase', 'anonymous',
'debug'. Existing rows (predating this column) default to 'unknown'.
"""

import uuid as _uuid_mod
from typing import NamedTuple, Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings
from models.schemas import TripState

# auto_error=False lets us return clearer 401s and run the dev fallback below.
_bearer = HTTPBearer(auto_error=False)

# The canonical UUID form is lowercase hyphenated: 8-4-4-4-12.
# Our client always sends this form. Anything else (uppercase, braced,
# urn:uuid:, hyphenless) signals a hand-rolled request and is rejected.
_CANONICAL_UUID_RE_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class ResolvedIdentity(NamedTuple):
    """The result of identity resolution: who, and how they were identified."""
    user_id: str
    identity_kind: str  # 'supabase' | 'anonymous' | 'debug'


def _validate_anonymous_uuid(value: str) -> str:
    """Validate and canonicalise a UUID v4 for anonymous identity.

    Returns the canonical (lowercase hyphenated) form.
    Raises HTTPException if:
    - Not a valid UUID at all
    - Not version 4 (v1 embeds device MAC -- real PII leak)
    - Not RFC 4122 variant
    - Not already in canonical form (our client only sends canonical;
      anything else is a hand-rolled or intercepted request)
    """
    try:
        parsed = _uuid_mod.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid anonymous identity: not a valid UUID",
        )

    if parsed.version != 4:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid anonymous identity: must be UUID version 4 "
                "(RFC 4122 variant). Version 1 UUIDs are rejected because "
                "they embed the device MAC address."
            ),
        )

    if parsed.variant != _uuid_mod.RFC_4122:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid anonymous identity: must have RFC 4122 variant bits",
        )

    canonical = str(parsed)
    if value != canonical:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid anonymous identity: UUID must be in canonical form "
                "(lowercase hyphenated). Our client always sends canonical; "
                "non-canonical forms are rejected."
            ),
        )

    return canonical


def _parse_anonymous_header(authorization: Optional[str]) -> Optional[str]:
    """Parse Authorization: Anonymous <uuid> and return the raw UUID value, or None.

    We parse the raw Authorization header rather than relying on HTTPBearer
    because HTTPBearer only accepts the Bearer scheme and would reject
    'Authorization: Anonymous <uuid>' before our code runs.
    """
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "anonymous":
        return None
    return value.strip()


def _decode_supabase_jwt(token: str) -> str:
    """Verify a Supabase access token and return its subject (user_id)."""
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    return user_id


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
    # --- Path 1: Real JWT auth (takes precedence when secret configured) ---
    if settings.supabase_jwt_secret:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = _decode_supabase_jwt(credentials.credentials)
        return ResolvedIdentity(user_id=user_id, identity_kind="supabase")

    # --- Path 2: Anonymous device identity (SPEC-09) ---
    anon_raw = _parse_anonymous_header(authorization)
    if anon_raw is not None:
        if not settings.allow_anonymous:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Anonymous identity is not enabled (TB_ALLOW_ANONYMOUS=false)",
            )
        canonical_uuid = _validate_anonymous_uuid(anon_raw)
        return ResolvedIdentity(user_id=canonical_uuid, identity_kind="anonymous")

    # --- Path 3: Debug fallback ---
    if settings.debug:
        if not x_debug_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Auth not configured. In debug mode, pass an 'X-Debug-User-Id' "
                    "header, or set TB_SUPABASE_JWT_SECRET to enable real auth."
                ),
            )
        return ResolvedIdentity(user_id=x_debug_user_id, identity_kind="debug")

    # --- Path 4: Misconfigured production ---
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server auth misconfiguration: TB_SUPABASE_JWT_SECRET is not set",
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
