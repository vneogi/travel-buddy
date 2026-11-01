"""SPEC-43 Gap 10: strip request values from validation errors.

Pydantic's ``RequestValidationError.errors()`` dicts carry ``input`` (the raw
field value), ``ctx`` and ``url``. A traveller who pastes a booking code or
token into the wrong field must not see it echoed back, logged, or kept in
the error ring. This is a key allowlist (type, loc, msg), not secret-literal
replacement (see monitoring/redact.py for that).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

PUBLIC_ERROR_KEYS = ("type", "loc", "msg")


def _public_loc(loc: Any) -> List[Any]:
    out: List[Any] = []
    for segment in loc if isinstance(loc, (list, tuple)) else (loc,):
        out.append(segment if isinstance(segment, (str, int)) else str(segment))
    return out


def public_validation_errors(errors: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return each error with only type, loc and msg (missing keys omitted)."""
    public: List[Dict[str, Any]] = []
    for err in errors or []:
        if not isinstance(err, dict):
            continue
        item: Dict[str, Any] = {}
        if err.get("type") is not None:
            item["type"] = str(err["type"])
        if err.get("loc") is not None:
            item["loc"] = _public_loc(err["loc"])
        if err.get("msg") is not None:
            item["msg"] = str(err["msg"])
        public.append(item)
    return public
