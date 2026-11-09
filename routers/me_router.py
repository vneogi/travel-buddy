"""SPEC-43 Gap 4 slice 6: authenticated self-service erase.

POST /api/v1/me/erase   body {"confirm": "erase-my-data"}

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

Remainders, not handled here: a still-unexpired access token may verify at
the API until exp (no denylist this slice; Gap 6 records it). No tombstone,
cache/error-ring purge, export, retention job or Flutter flow.
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
from services.data_rights_erase import EraseBackend, execute_erase
from services.data_rights_erase_supabase import SupabaseEraseBackend

logger = logging.getLogger("travelbuddy")

router = APIRouter(prefix="/api/v1", tags=["me"])

ERASE_CONFIRMATION = "erase-my-data"
ERASE_UNAVAILABLE = "erase_unavailable"
ERASE_INCOMPLETE = "erase_incomplete"


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
