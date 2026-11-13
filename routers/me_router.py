"""SPEC-43 Gap 4 slice 6: authenticated self-service erase.

POST /api/v1/me/erase   body {"confirm": "erase-my-data"}
GET  /api/v1/me/export  (slice 14, see the export notes below)

- Erases only the authenticated caller (resolve_identity). No user id is
  read from the path, query or body; extra body fields are 422.
- The confirmation must be exactly "erase-my-data" (422 otherwise). A
  request without valid credentials is rejected (401) by resolve_identity
  before the backend dependency runs.
- The backend comes from get_erase_backend: SupabaseEraseBackend over the
  configured Supabase client when IS_SUPABASE, otherwise 501
  erase_unavailable. The in-memory dev DatabaseService is not wired this
  slice, and there is never a fallback to a different backend.
- Any backend failure returns 500 {"detail": "erase_incomplete"} with no
  exception text, table, user id or class name, and logs one WARNING with
  the exception class name and request id only. No retry inside the route.
- Safe to call again: each step deletes only rows that still exist, so a
  repeat run on a partly erased account completes the remaining steps.
- The response carries only table names and row counts.
- Does not create the user record (get_or_create_user is never called).
- Slice 7: after the row erase succeeds, and only for
  identity_kind == "supabase", the caller's Supabase Auth (GoTrue) identity
  is deleted through get_auth_deleter. Rows first, Auth second, so a failed
  row erase never leaves a traveller unable to sign in to retry. Debug
  identities have no GoTrue user and never reach the deleter. An Auth
  delete failure takes the same generic 500 path; the row erase is not
  rolled back (no transaction spans PostgREST and GoTrue). A retry finds
  zero rows and retries the Auth delete; an already-missing Auth user is
  success.

- Slice 8: after the row erase (and, for supabase, the Auth delete)
  succeeds, the caller's user_id is denied in this process for
  DENY_TTL_SECONDS, for every identity kind including debug.
  resolve_identity then answers 401 for that id, so a still-unexpired
  token cannot keep working or recreate a user_tiers row here. If the Auth
  delete fails nothing is denied, so the traveller can retry.

- Slice 9: before the deny step, the caller's in-process semantic-cache
  entries, cost-tracker events and Ask budget counter are purged, for
  every identity kind. If the purge raises, the generic 500 is returned
  and the caller is not denied, so they can retry.

Remainders, not handled here: error-ring purge by identity (entries carry
no user id), the Ask exact-match public cache, cached_responses SQL rows,
a denylist shared across Cloud Run instances (and per-jti), tombstones,
export, retention jobs and the Flutter flow.

Slice 14, export: GET /api/v1/me/export returns the authenticated caller's
identity rows as the flat per-table result of execute_export (table name
plus row list, in EXPORT_STEPS order; method and via are not returned). The
user id comes only from resolve_identity, never from the path, query or
body. The backend comes from get_export_backend: SupabaseExportBackend when
IS_SUPABASE, otherwise 501 export_unavailable, with no fallback store. Any
failure returns 500 {"detail": "export_incomplete"} and logs one WARNING
with the exception class name and request id only. Export never deletes
Auth, denies or purges caches, and never creates the user record.
Remainders: nesting under trips, a human-readable or downloadable document,
pagination, and rate limiting (the Gap 11 limiter does not count GET, so
export is not throttled yet).
"""

import importlib
import logging
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from security import ResolvedIdentity, resolve_identity
from services.data_rights_auth_delete import (
    AuthIdentityDeleter,
    NoOpAuthIdentityDeleter,
    SupabaseAuthIdentityDeleter,
)
from services.data_rights_cache_purge import purge_identity_caches
from services.data_rights_token_deny import deny_identity
from services.data_rights_erase import EraseBackend, execute_erase
from services.data_rights_erase_supabase import SupabaseEraseBackend
from services.data_rights_export import ExportBackend, execute_export
from services.data_rights_export_supabase import SupabaseExportBackend

logger = logging.getLogger("travelbuddy")

router = APIRouter(prefix="/api/v1", tags=["me"])

ERASE_CONFIRMATION = "erase-my-data"
ERASE_UNAVAILABLE = "erase_unavailable"
ERASE_INCOMPLETE = "erase_incomplete"
EXPORT_UNAVAILABLE = "export_unavailable"
EXPORT_INCOMPLETE = "export_incomplete"


class EraseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal["erase-my-data"]


class ErasedTable(BaseModel):
    table: str
    rows: int


class EraseResponse(BaseModel):
    status: Literal["erased"]
    tables: List[ErasedTable]


def get_erase_backend() -> EraseBackend:
    """Supabase erase backend, or 501 when Supabase is not configured."""
    # importlib: the services package attribute may shadow the submodule.
    provider = importlib.import_module("services.db_provider")
    if not provider.IS_SUPABASE:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=ERASE_UNAVAILABLE)
    return SupabaseEraseBackend(provider.db_service.client)


def get_auth_deleter() -> AuthIdentityDeleter:
    """GoTrue deleter when Supabase is configured, otherwise a no-op."""
    provider = importlib.import_module("services.db_provider")
    if not provider.IS_SUPABASE:
        return NoOpAuthIdentityDeleter()
    return SupabaseAuthIdentityDeleter(provider.db_service.client)


@router.post("/me/erase", response_model=EraseResponse)
async def erase_me(
    request: Request,
    body: EraseRequest,
    identity: ResolvedIdentity = Depends(resolve_identity),
    backend: EraseBackend = Depends(get_erase_backend),
    auth_deleter: AuthIdentityDeleter = Depends(get_auth_deleter),
):
    """Erase the caller's server rows, then their Auth identity."""
    try:
        results = execute_erase(identity.user_id, backend)
        # Only after every row step succeeded. Debug identities never reach it.
        if identity.identity_kind == "supabase":
            auth_deleter.delete_auth_user(identity.user_id)
        # In-process caches next, then deny last: only after rows, (for
        # supabase) Auth and the purge all succeeded.
        purge_identity_caches(identity.user_id)
        deny_identity(identity.user_id)
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning("erase incomplete (%s) request_id=%s", type(exc).__name__, request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": ERASE_INCOMPLETE},
        )
    return {
        "status": "erased",
        "tables": [{"table": r["table"], "rows": r["rows"]} for r in results],
    }


# --- slice 14: export -------------------------------------------------------


class ExportedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    rows: List[dict]


class ExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["exported"]
    tables: List[ExportedTable]


def get_export_backend() -> ExportBackend:
    """Supabase export backend, or 501 when Supabase is not configured."""
    # importlib: the services package attribute may shadow the submodule.
    provider = importlib.import_module("services.db_provider")
    if not provider.IS_SUPABASE:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=EXPORT_UNAVAILABLE)
    return SupabaseExportBackend(provider.db_service.client)


@router.get("/me/export", response_model=ExportResponse)
async def export_me(
    request: Request,
    identity: ResolvedIdentity = Depends(resolve_identity),
    backend: ExportBackend = Depends(get_export_backend),
):
    """Export the caller's identity rows, flat per table."""
    try:
        results = execute_export(identity.user_id, backend)
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning("export incomplete (%s) request_id=%s", type(exc).__name__, request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": EXPORT_INCOMPLETE},
        )
    return {
        "status": "exported",
        "tables": [{"table": r["table"], "rows": r["rows"]} for r in results],
    }
