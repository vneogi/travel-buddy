"""Travel Buddy -- Authentication & Authorization.

Resolution order (SPEC-09):
1. Real Supabase JWT (when TB_SUPABASE_JWT_SECRET set) -- verified user
2. Authorization: Anonymous <uuid-v4> -- device identity (when TB_ALLOW_ANONYMOUS=true
   AND no JWT secret configured). UUID must be version 4 with correct variant bits;
   version 1 UUIDs embed the device MAC address, which is a PII leak.
3. X-Debug-User-Id -- only when no JWT secret AND TB_DEBUG=true
4. Otherwise 401

TB_ALLOW_ANONYMOUS defaults to False (fail-closed). Deployments that accept
anonymous device identities must opt in explicitly.
"""

import uuid as _uuid_mod
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings
from models.schemas import TripState

# auto_error=False lets us return clearer 401s and run the dev fallback below.
_bearer = HTTPBearer(auto_error=False)


def _is_valid_uuid_v4(value: str) -> bool:
    """Validate that value is a UUID version 4 with RFC 4122 variant bits.

    Rejects v1 UUIDs (embed device MAC -- real privacy leak in an app claiming
    no PII), v3/v5 (deterministic from input), nil, and malformed strings.
    """
    try:
        parsed = _uuid_mod.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    # Version must be 4 (random)
    if parsed.version != 4:
        return False
    # Variant must be RFC 4122 (variant bits 10xx)
    if parsed.variant != _uuid_mod.RFC_4122:
        return False
    return True


def _parse_anonymous_header(authorization: Optional[str]) -> Optional[str]:
    """Parse Authorization: Anonymous <uuid> and return the UUID, or None.

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


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    authorization: Optional[str] = Header(default=None),
    x_debug_user_id: Optional[str] = Header(default=None),
) -> str:
    """FastAPI dependency: return the authenticated user's ID.

    Production: requires a valid Authorization: Bearer <supabase_jwt> header.
    Anonymous: Authorization: Anonymous <uuid-v4> when TB_ALLOW_ANONYMOUS=true
    and no JWT secret is configured.
    Local dev (only when TB_SUPABASE_JWT_SECRET is unset AND TB_DEBUG is true):
    falls back to the X-Debug-User-Id header so the app is testable without
    real tokens.
    """
    # --- Path 1: Real JWT auth (takes precedence when secret configured) ---
    if settings.supabase_jwt_secret:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _decode_supabase_jwt(credentials.credentials)

    # --- Path 2: Anonymous device identity (SPEC-09) ---
    anon_uuid = _parse_anonymous_header(authorization)
    if anon_uuid is not None:
        if not settings.allow_anonymous:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Anonymous identity is not enabled (TB_ALLOW_ANONYMOUS=false)",
            )
        if not _is_valid_uuid_v4(anon_uuid):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Invalid anonymous identity: must be a valid UUID version 4 "
                    "(RFC 4122 variant). Version 1 UUIDs are rejected because they "
                    "embed the device MAC address."
                ),
            )
        return anon_uuid

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
        return x_debug_user_id

    # --- Path 4: Misconfigured production ---
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server auth misconfiguration: TB_SUPABASE_JWT_SECRET is not set",
    )


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
