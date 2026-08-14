"""Tests: provenance is persisted through record_signal (SPEC-02 Part C).

Asserts on what get_signal returns -- not on _compute_provenance's return value.
The helper already works; testing it again would have missed the real bug (the
return being discarded in the write path).
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routers.signal_router import _compute_provenance
from services.database_service import DatabaseService


def _fresh_id():
    return str(uuid.uuid4())


class TestProvenancePersisted:
    """clock_skew_seconds is persisted when skew > 1h, absent otherwise."""

    def test_stale_signal_carries_clock_skew(self):
        """Signal captured > 1 hour ago persists clock_skew_seconds."""
        svc = DatabaseService()
        sig_id = _fresh_id()
        captured = datetime.now(tz=timezone.utc) - timedelta(hours=3)

        provenance = _compute_provenance(captured)
        svc.record_signal(
            user_id=_fresh_id(),
            signal_id=sig_id,
            signal_type="dish_reaction",
            place_ref="place_123",
            captured_at=captured,
            provenance=provenance,
        )
        stored = svc.get_signal(sig_id)
        assert stored is not None
        assert "provenance" in stored
        assert stored["provenance"]["method"] == "client_emit"
        assert "clock_skew_seconds" in stored["provenance"], (
            "Stale signal must carry clock_skew_seconds in provenance"
        )
        # 3 hours = ~10800 seconds (allow some slack for test execution)
        assert stored["provenance"]["clock_skew_seconds"] > 3500

    def test_fresh_signal_has_no_clock_skew(self):
        """Signal captured just now does NOT carry clock_skew_seconds."""
        svc = DatabaseService()
        sig_id = _fresh_id()
        captured = datetime.now(tz=timezone.utc) - timedelta(seconds=30)

        provenance = _compute_provenance(captured)
        svc.record_signal(
            user_id=_fresh_id(),
            signal_id=sig_id,
            signal_type="dish_reaction",
            place_ref="place_456",
            captured_at=captured,
            provenance=provenance,
        )
        stored = svc.get_signal(sig_id)
        assert stored is not None
        assert "provenance" in stored
        assert stored["provenance"]["method"] == "client_emit"
        assert "clock_skew_seconds" not in stored["provenance"], (
            "Fresh signal must NOT carry clock_skew_seconds"
        )

    def test_no_provenance_param_falls_back_to_default(self):
        """Callers that omit provenance= still get the default dict stored."""
        svc = DatabaseService()
        sig_id = _fresh_id()

        svc.record_signal(
            user_id=_fresh_id(),
            signal_id=sig_id,
            signal_type="dish_reaction",
            place_ref="place_789",
            captured_at=datetime.now(tz=timezone.utc),
        )
        stored = svc.get_signal(sig_id)
        assert stored["provenance"] == {"method": "client_emit"}
