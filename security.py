"""Travel Buddy - Authentication & Authorization.

Verifies Supabase-issued JWTs and exposes FastAPI dependencies that make the
authenticated user's ID the single source of truth for every request. Clients
can no longer act on behalf of an arbitrary ``user_id`` supplied in the body or
path (the previous IDOR hole).

Supabase signs access tokens with the project's JWT secret (HS256), sets the
``sub`` claim to the user's UUID, and ``aud`` to ``"authenticated"``. Set
``TB_SUPABASE_JWT_SECRET`` (Project Settings -> API -> JWT Secret) to enable
verification. (If your project uses the newer asymmetric signing keys, verify
via JWKS instead — ask and I'll provide that variant.)
"""

from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings
from models.schemas import TripState

# auto_error=False lets us return clearer 401s and run the dev fallback below.
_bearer = HTTPBearer(auto_error=False)


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
    x_debug_user_id: Optional[str] = Header(default=None),
) -> str:
    """FastAPI dependency: return the authenticated user's ID.

    Production: requires a valid ``Authorization: Bearer <supabase_jwt>`` header.
    Local dev (only when TB_SUPABASE_JWT_SECRET is unset AND TB_DEBUG is true):
    falls back to the ``X-Debug-User-Id`` header so the app is testable without
    real tokens. The fallback is refused whenever a JWT secret is configured or
    debug is off, so production always fails closed.
    """
    # Debug mode: accept X-Debug-User-Id header for testing, even if JWT secret
    # is configured. This lets tests and local dev work without real tokens.
    if settings.debug and x_debug_user_id:
        return x_debug_user_id

    if settings.supabase_jwt_secret:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _decode_supabase_jwt(credentials.credentials)

    # No JWT secret configured and no debug header.
    if settings.debug:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Auth not configured. In debug mode, pass an 'X-Debug-User-Id' "
                "header, or set TB_SUPABASE_JWT_SECRET to enable real auth."
            ),
        )

    # Misconfigured production: never serve unauthenticated traffic.
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server auth misconfiguration: TB_SUPABASE_JWT_SECRET is not set",
    )


def require_trip_owner(trip: Optional[TripState], user_id: str) -> TripState:
    """Return the trip if it exists and belongs to ``user_id``; else raise.

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
