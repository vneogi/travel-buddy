"""Tests: provenance is persisted through the signal ingest endpoint (SPEC-02 Part C).

Drives POST /api/v1/signals -- the production write path. Does NOT call
_compute_provenance directly; the router is responsible for computing and
passing provenance to record_signal. Asserting on what get_signal returns
after an endpoint call is the only way to prove the router actually wires it.
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service


def _fresh_id():
    return str(uuid.uuid4())


def _post_signal(client, signal_id: str, captured_at: datetime):
    """POST a single signal through the ingest endpoint."""
    return client.post(
        "/api/v1/signals",
        headers={"X-Debug-User-Id": "provenance-test-user"},
        json={
            "signals": [
                {
                    "signal_id": signal_id,
                    "signal_type": "user_loved",
                    "place_ref": "test_venue_123",
                    "captured_at": captured_at.isoformat(),
                }
            ]
        },
    )


class TestProvenancePersistedViaRouter:
    """clock_skew_seconds reaches the DB through the router, not just in isolation."""

    def test_stale_signal_carries_clock_skew(self):
        """Signal captured > 1 hour ago persists clock_skew_seconds via router."""
        client = TestClient(app)
        sig_id = _fresh_id()
        captured = datetime.now(tz=timezone.utc) - timedelta(hours=3)

        resp = _post_signal(client, sig_id, captured)
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1

        stored = db_service.get_signal(sig_id)
        assert stored is not None, "Signal not found after ingest"
        assert "provenance" in stored, "provenance field missing from stored signal"
        assert stored["provenance"]["method"] == "client_emit"
        assert "clock_skew_seconds" in stored["provenance"], (
            "Stale signal must carry clock_skew_seconds in provenance"
        )
        # 3 hours ~= 10800s (allow slack for test execution time)
        assert stored["provenance"]["clock_skew_seconds"] > 3500

    def test_fresh_signal_has_no_clock_skew(self):
        """Signal captured just now does NOT carry clock_skew_seconds."""
        client = TestClient(app)
        sig_id = _fresh_id()
        captured = datetime.now(tz=timezone.utc) - timedelta(seconds=10)

        resp = _post_signal(client, sig_id, captured)
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1

        stored = db_service.get_signal(sig_id)
        assert stored is not None, "Signal not found after ingest"
        assert "provenance" in stored, "provenance field missing from stored signal"
        assert stored["provenance"]["method"] == "client_emit"
        assert "clock_skew_seconds" not in stored["provenance"], (
            "Fresh signal must NOT carry clock_skew_seconds"
        )
