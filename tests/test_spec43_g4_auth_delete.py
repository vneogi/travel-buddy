"""SPEC-43 Gap 4 slice 7: Auth identity deleter units (fake admin client)."""

import ast
from pathlib import Path

import pytest

from services import data_rights_auth_delete as auth_module
from services.data_rights_auth_delete import (
    NoOpAuthIdentityDeleter,
    SupabaseAuthIdentityDeleter,
    _is_missing_user,
)

USER_ID = "8a3c1f4e-0000-4000-8000-00000000g4ad"


class _Admin:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def delete_user(self, *args, **kwargs):
        self.calls.append(("delete_user", args, kwargs))
        if self.error is not None:
            raise self.error

    def __getattr__(self, name):
        # Any other admin method (list_users, bulk delete, ...) is a bug.
        raise AssertionError(f"unexpected admin method {name}")


class _Auth:
    def __init__(self, admin):
        self.admin = admin


class FakeClient:
    def __init__(self, error=None):
        self.admin = _Admin(error)
        self.auth = _Auth(self.admin)


class _ApiError(Exception):
    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code


class _HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_supabase_auth_delete_calls_admin_with_string_id():
    client = FakeClient()
    assert SupabaseAuthIdentityDeleter(client).delete_auth_user(USER_ID) is None
    assert client.admin.calls == [("delete_user", (USER_ID,), {})]
    assert isinstance(client.admin.calls[0][1][0], str)


@pytest.mark.parametrize("bad", [None, "", "   ", 123, b"abc"])
def test_supabase_auth_delete_rejects_blank_user_id_before_any_call(bad):
    client = FakeClient()
    with pytest.raises(ValueError):
        SupabaseAuthIdentityDeleter(client).delete_auth_user(bad)
    assert client.admin.calls == []


@pytest.mark.parametrize(
    "error",
    [
        _HttpError(404),
        _ApiError("User not found", status=404),
        _ApiError("user not found"),
        _ApiError("Not Found"),
        _ApiError("gotrue error", code="user_not_found"),
        _ApiError("missing", status="404"),
    ],
)
def test_supabase_auth_delete_missing_user_is_success(error):
    client = FakeClient(error=error)
    SupabaseAuthIdentityDeleter(client).delete_auth_user(USER_ID)
    assert client.admin.calls == [("delete_user", (USER_ID,), {})]
    assert _is_missing_user(error)


@pytest.mark.parametrize(
    "error",
    [
        _HttpError(500),
        _HttpError(403),
        _ApiError("Database error deleting user", status=500),
        RuntimeError("connection reset"),
        TimeoutError("timed out"),
    ],
)
def test_supabase_auth_delete_other_errors_propagate(error):
    client = FakeClient(error=error)
    with pytest.raises(type(error)) as excinfo:
        SupabaseAuthIdentityDeleter(client).delete_auth_user(USER_ID)
    assert excinfo.value is error
    assert not _is_missing_user(error)
    assert len(client.admin.calls) == 1


def test_noop_auth_delete_never_touches_a_client():
    deleter = NoOpAuthIdentityDeleter()
    assert deleter.delete_auth_user(USER_ID) is None
    assert not hasattr(deleter, "_client")
    for bad in (None, "", "  "):
        with pytest.raises(ValueError):
            deleter.delete_auth_user(bad)


def test_auth_deleter_has_no_supabase_import():
    source = Path(auth_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert "supabase" not in roots and "gotrue" not in roots
    assert roots <= {"__future__", "typing"}, roots
    assert "print(" not in source and "logging" not in source
