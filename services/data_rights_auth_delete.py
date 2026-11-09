"""SPEC-43 Gap 4 slice 7: delete the caller's Supabase Auth (GoTrue) identity.

Called by POST /api/v1/me/erase only after the row erase has succeeded, and
only for identity_kind == "supabase". Rows first, Auth second: if Auth went
first and the row erase failed, the traveller could not authenticate to
retry. A user that is already gone counts as success, so a retry is safe.

The admin client is injected. This module does not import supabase, does not
log and does not print. It only ever calls client.auth.admin.delete_user with
one id; it never lists users and never issues a bulk delete. ASCII only.
"""

from __future__ import annotations

from typing import Any, Protocol


class AuthIdentityDeleter(Protocol):
    def delete_auth_user(self, user_id: str) -> None: ...


def _check_user_id(user_id: Any) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required")
    return user_id


def _is_missing_user(exc: BaseException) -> bool:
    """True when the admin error means the Auth user does not exist.

    Inspects the exception object only (no supabase exception types).
    """
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if value is not None and str(value).strip() == "404":
            return True
    texts = [str(exc)]
    message = getattr(exc, "message", None)
    if message is not None:
        texts.append(str(message))
    code = getattr(exc, "code", None)
    if code is not None:
        texts.append(str(code))
    return any("not found" in t.lower() or "user_not_found" in t.lower() for t in texts)


class NoOpAuthIdentityDeleter:
    """Used when Supabase is not configured: validates the id, does nothing."""

    def delete_auth_user(self, user_id: str) -> None:
        _check_user_id(user_id)


class SupabaseAuthIdentityDeleter:
    """Deletes one GoTrue user through client.auth.admin.delete_user."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def delete_auth_user(self, user_id: str) -> None:
        user_id = _check_user_id(user_id)
        try:
            self._client.auth.admin.delete_user(str(user_id))
        except Exception as exc:
            if _is_missing_user(exc):
                return
            raise
