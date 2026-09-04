"""Tests for signal capture endpoint (SPEC-01 Part B + SPEC-02 Part C).

Verifies:
1. Valid signal -> 200, accepted:1
2. Idempotency: re-POST same signal_id -> 200, duplicates:1, still one row
3. Unknown signal_type -> itemized in rejected[] (SPEC-02 Part C)
4. No auth -> 401
5. captured_at preserved verbatim (SPEC-02 Part C)
6. captured_at too old -> rejected per-item, not 500 (SPEC-02 Part C)
7. captured_at slightly future -> accepted (clock tolerance)
8. Mixed batch: some valid, some rejected -> partial success (SPEC-02 Part C)
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service

client = TestClient(app)

# Auth header for debug mode (TB_SUPABASE_JWT_SECRET unset + TB_DEBUG=true)
DEBUG_USER = "11111111-1111-1111-1111-111111111111"
AUTH_HEADERS = {"X-Debug-User-Id": DEBUG_USER}


@pytest.fixture(autouse=True)
def reset_signals():
    """Clear signal store between tests."""
    db_service._signals.clear()
    yield


class TestSignalIngest:
    """POST /api/v1/signals"""

    def _make_signal(
        self,
        signal_id="aaaaaaaa-1111-2222-3333-444444444444",
        signal_type="user_loved",
        place_ref="dubai-mall",
        captured_at=None,
    ):
        if captured_at is None:
            captured_at = datetime.now(tz=timezone.utc).isoformat()
        return {
            "signal_id": signal_id,
            "signal_type": signal_type,
            "place_ref": place_ref,
            "value_text": "loved",
            "captured_at": captured_at,
            "trip_id": "trip-001",
        }

    def test_valid_signal_accepted(self):
        """A valid user_loved signal is accepted."""
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [self._make_signal()]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["duplicates"] == 0
        assert data["rejected"] == []

        # Verify it's stored
        assert db_service.get_signals_count() == 1
        stored = db_service.get_signal("aaaaaaaa-1111-2222-3333-444444444444")
        assert stored is not None
        assert stored["user_id"] == DEBUG_USER
        assert stored["signal_type"] == "user_loved"
        assert stored["place_ref"] == "dubai-mall"

    def test_idempotency_duplicate_signal_id(self):
        """Re-posting the same signal_id is a 200 no-op, not a duplicate row."""
        sig = self._make_signal()
        # First post
        resp1 = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp1.status_code == 200
        assert resp1.json()["accepted"] == 1

        # Second post -- same signal_id
        resp2 = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        assert resp2.json()["accepted"] == 0
        assert resp2.json()["duplicates"] == 1

        # Still only one row
        assert db_service.get_signals_count() == 1

    def test_batch_multiple_signals(self):
        """A batch with multiple distinct signals records all of them."""
        signals = [
            self._make_signal(signal_id="sig-001", place_ref="burj-khalifa"),
            self._make_signal(signal_id="sig-002", place_ref="dubai-mall"),
            self._make_signal(signal_id="sig-003", place_ref="la-mer"),
        ]
        resp = client.post(
            "/api/v1/signals",
            json={"signals": signals},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 3
        assert resp.json()["duplicates"] == 0
        assert db_service.get_signals_count() == 3

    def test_unknown_signal_type_rejected_per_item(self):
        """Unknown signal_type -> itemized in rejected[] (not 500 for whole batch).

        SPEC-02 Part C: per-item rejection so client can mark as failed_permanent.
        """
        sig = self._make_signal(signal_type="totally_fake_type")
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 0
        assert data["rejected"][0]["signal_id"] == sig["signal_id"]
        assert "totally_fake_type" in data["rejected"][0]["reason"]

    def test_no_auth_rejected(self):
        """No auth header -> 401."""
        sig = self._make_signal()
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            # No headers -- no auth
        )
        assert resp.status_code == 401

    def test_user_id_from_token_not_body(self):
        """user_id in the stored signal comes from the auth token, not the payload."""
        sig = self._make_signal()
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers={"X-Debug-User-Id": "attacker-id-999"},
        )
        assert resp.status_code == 200
        stored = db_service.get_signal("aaaaaaaa-1111-2222-3333-444444444444")
        assert stored["user_id"] == "attacker-id-999"  # gets whatever token says
        # Key point: there's no way for a client to set user_id to someone
        # else's -- the token IS the identity. No IDOR.

    # ==================================================================
    # SPEC-02 Part C tests
    # ==================================================================

    def test_captured_at_preserved_verbatim(self):
        """captured_at from client is stored as-is (never overwritten by server).

        SPEC-02 invariant #5: trust device clock for captured_at.
        """
        # Use a specific timestamp that we'll verify is stored exactly
        ts = (datetime.now(tz=timezone.utc) - timedelta(days=2)).replace(
            microsecond=0
        ).isoformat()
        sig = self._make_signal(signal_id="ts-test-001", captured_at=ts)
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        stored = db_service.get_signal("ts-test-001")
        # The stored captured_at should match what the client sent
        assert datetime.fromisoformat(stored["captured_at"]) == datetime.fromisoformat(ts)

    def test_captured_at_old_but_within_30d_accepted(self):
        """A captured_at up to 30 days old is accepted (long offline is normal).

        SPEC-02 Part C: tolerate up to 30 days.
        """
        # 20 days ago -- well within tolerance
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=20)).isoformat()
        sig = self._make_signal(signal_id="old-ok-001", captured_at=old_ts)
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1
        assert resp.json()["rejected"] == []

    def test_captured_at_too_old_rejected(self):
        """A captured_at > 30 days old is rejected per-item (not 500).

        SPEC-02 Part C: reject but don't crash the batch.
        """
        ancient_ts = (datetime.now(tz=timezone.utc) - timedelta(days=45)).isoformat()
        sig = self._make_signal(signal_id="ancient-001", captured_at=ancient_ts)
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 0
        assert len(data["rejected"]) == 1
        assert data["rejected"][0]["signal_id"] == "ancient-001"
        assert "too old" in data["rejected"][0]["reason"]

    def test_captured_at_slightly_future_accepted(self):
        """A captured_at slightly in the future (clock drift) is accepted.

        SPEC-02 Part C: 5-minute tolerance for client clock drift.
        """
        future_ts = (datetime.now(tz=timezone.utc) + timedelta(minutes=2)).isoformat()
        sig = self._make_signal(signal_id="future-ok-001", captured_at=future_ts)
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1

    def test_captured_at_far_future_rejected(self):
        """A captured_at far in the future is rejected (clearly wrong clock)."""
        far_future = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
        sig = self._make_signal(signal_id="future-bad-001", captured_at=far_future)
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 0
        assert data["rejected"][0]["signal_id"] == "future-bad-001"
        assert "future" in data["rejected"][0]["reason"]

    def test_mixed_batch_partial_success(self):
        """A batch with some good and some bad signals: good accepted, bad rejected.

        SPEC-02 Part C: never 500 the whole batch for one bad item.
        """
        signals = [
            self._make_signal(signal_id="good-001", place_ref="burj-khalifa"),
            self._make_signal(signal_id="bad-type-001", signal_type="nonexistent"),
            self._make_signal(signal_id="good-002", place_ref="dubai-mall"),
        ]
        resp = client.post(
            "/api/v1/signals",
            json={"signals": signals},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 2
        assert data["duplicates"] == 0
        assert len(data["rejected"]) == 1
        assert data["rejected"][0]["signal_id"] == "bad-type-001"
        # Good ones were still stored
        assert db_service.get_signals_count() == 2
