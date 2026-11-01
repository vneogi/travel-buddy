"""SPEC-43 Gap 10: client 422 bodies never echo request values.

Only type/loc/msg leave the validation handler: in the response, the error
ring, and the validation log line. No widgets, no live Postgres.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from main import app
from monitoring.error_log import error_log
from monitoring.validation_public import public_validation_errors
from tests.test_spec40_guided_create import _range_body

client = TestClient(app)
HEADERS = {"X-Debug-User-Id": "user-g10-422"}
CANARY = "sk-CANARY-g10-422-do-not-echo"
CREATE_CANARY = "CANARY-interest-string-g10"


@pytest.fixture(autouse=True)
def _clear_ring():
    error_log.clear()
    yield
    error_log.clear()


def _bad_event():
    return client.post(
        "/api/v1/trip/event",
        json={"trip_id": 12345, "message": CANARY},
        headers=HEADERS,
    )


def test_422_does_not_echo_request_values():
    r = _bad_event()
    assert r.status_code == 422
    assert CANARY not in r.text
    body = r.json()
    assert set(body) == {"detail", "request_id"}
    assert body["request_id"]
    detail = body["detail"]
    assert isinstance(detail, list) and detail
    for err in detail:
        assert set(err) <= {"type", "loc", "msg"}
        for forbidden in ("input", "ctx", "url"):
            assert forbidden not in err
        assert isinstance(err["loc"], list)


def test_422_create_invalid_interests_stays_typed():
    body = _range_body(num_days=2)
    body["preferences"] = {"interest_ids": CREATE_CANARY}
    r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_interests"
    assert isinstance(detail["message"], str) and detail["message"]
    assert CREATE_CANARY not in r.text


def test_422_ring_entry_is_stripped():
    _bad_event()
    entries = error_log.recent()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["exc_type"] == "RequestValidationError"
    assert entry["status"] == 422
    assert CANARY not in json.dumps(entries)
    assert "'input'" not in entry["message"]


def test_422_log_line_is_stripped(caplog):
    with caplog.at_level(logging.WARNING, logger="travelbuddy"):
        _bad_event()
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Validation error on POST /api/v1/trip/event" in logged
    assert CANARY not in logged
    assert "'input'" not in logged


def test_public_validation_errors_allowlist():
    raw = [
        {
            "type": "string_type",
            "loc": ("body", "trip_id"),
            "msg": "Input should be a valid string",
            "input": CANARY,
            "ctx": {"error": ValueError(CANARY)},
            "url": "https://errors.pydantic.dev/2/v/string_type",
        },
        {"loc": ("body", 0, object()), "input": CANARY},
    ]
    public = public_validation_errors(raw)
    assert public[0] == {
        "type": "string_type",
        "loc": ["body", "trip_id"],
        "msg": "Input should be a valid string",
    }
    assert set(public[1]) == {"loc"}
    assert public[1]["loc"][:2] == ["body", 0]
    assert CANARY not in json.dumps(public)
