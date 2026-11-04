"""SPEC-43 Gap 3: booking canaries are redacted from light completion and
API embedding payloads before they leave the process.

No network: LLMService.complete, litellm.embedding and litellm.aembedding are
replaced by capture doubles. Canaries go through the production methods (R17).
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.state_machine import TripStateMachine
from monitoring.redact import REDACTED, redact_outbound_llm_text
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService

PNR = "G3-CANARY-PNR-9f3a"
NOTE = "Window seat for G3-CANARY-NOTE"
USER_ID = "user-g3-redact-5b2e"


@pytest.fixture
def captured(monkeypatch):
    calls = []

    async def fake_complete(self, messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        return {"content": "ok", "model_used": "fake", "tokens": {}, "cost_usd": 0.0}

    monkeypatch.setattr(LLMService, "complete", fake_complete)
    return calls


def test_info_llm_payload_omits_booking_canary(captured):
    out = asyncio.run(
        LLMService().generate_info_response(
            f"What time is {PNR} at the pier?",
            context={"geo_region": "luang_prabang", "venue_name": "Wat Xieng Thong"},
            user_id=USER_ID,
            restricted_needles=[PNR],
        )
    )
    assert out == "ok"
    dumped = json.dumps(captured[0]["messages"])
    assert PNR not in dumped
    assert REDACTED in dumped
    assert "Wat Xieng Thong" in dumped
    assert captured[0]["user_id"] == USER_ID
    assert USER_ID not in dumped


def test_api_embedding_input_omits_booking_canary(monkeypatch):
    import litellm

    sent = []

    def fake_embedding(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.1, 0.2, 0.3]}])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    svc = EmbeddingService(use_synthetic=False)
    vec = svc._api_embedding(f"ferry for {PNR} tomorrow", user_id=USER_ID, restricted_needles=[PNR])
    assert vec == [0.1, 0.2, 0.3]
    assert len(sent) == 1
    dumped = json.dumps(sent[0]["input"])
    assert PNR not in dumped
    assert REDACTED in dumped


def test_batch_embeddings_input_omits_booking_canary(monkeypatch):
    import litellm

    sent = []

    async def fake_aembedding(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.0]} for _ in kwargs["input"]])

    monkeypatch.setattr(litellm, "aembedding", fake_aembedding)
    asyncio.run(
        LLMService().batch_embeddings(
            [f"where is {PNR}", "plain text"], user_id=USER_ID, restricted_needles=[PNR]
        )
    )
    dumped = json.dumps(sent[0]["input"])
    assert PNR not in dumped
    assert REDACTED in dumped
    assert "plain text" in dumped


def test_api_key_in_question_is_redacted_without_needles(monkeypatch):
    import litellm

    sent = []
    monkeypatch.setattr(
        litellm,
        "embedding",
        lambda **kw: sent.append(kw) or SimpleNamespace(data=[{"embedding": [0.0]}]),
    )
    EmbeddingService(use_synthetic=False)._api_embedding("use sk-live-0123456789abcdef please")
    assert "sk-live-0123456789abcdef" not in json.dumps(sent[0]["input"])


def test_synthetic_embedding_is_not_redacted():
    svc = EmbeddingService(use_synthetic=True)
    assert svc.generate_embedding(f"x {PNR}") == svc._synthetic_embedding(f"x {PNR}")
    assert svc.generate_embedding(f"x {PNR}") != svc._synthetic_embedding(f"x {REDACTED}")


def test_itinerary_user_message_omits_node_booking_canary(captured):
    trip_state = {
        "nodes": [
            {
                "venue_name": "Wat Xieng Thong",
                "confirmation_code": PNR,
                "booking_notes": NOTE,
                "lat": 19.876543,
                "lng": 102.134567,
            }
        ]
    }
    asyncio.run(
        LLMService().generate_itinerary_response(
            user_message=f"Move {PNR} later and keep {NOTE}.",
            trip_state=trip_state,
            venues_found=[{"name": "Utopia", "lat": 19.876543, "lng": 102.134567}],
            user_id=USER_ID,
        )
    )
    dumped = json.dumps(captured[0]["messages"])
    assert PNR not in dumped
    assert "G3-CANARY-NOTE" not in dumped
    assert "19.876543" not in dumped
    assert REDACTED in dumped
    assert "Wat Xieng Thong" in dumped


def test_short_needles_are_not_replaced():
    assert redact_outbound_llm_text("gate A1 at 10:00", ["A1", "  ab  ", "12345"]) == (
        "gate A1 at 10:00"
    )


def test_needles_longest_first_and_every_occurrence():
    text = "ABC123 and ABC123-XY and ABC123"
    out = redact_outbound_llm_text(text, ["ABC123", "ABC123-XY"])
    assert out == "REDACTED and REDACTED and REDACTED"


def test_empty_text_stays_empty():
    assert redact_outbound_llm_text("", [PNR]) == ""
    assert redact_outbound_llm_text(None, [PNR]) == ""


def test_orchestrator_light_needles_match_store_needles():
    node_a = SimpleNamespace(confirmation_code=PNR, booking_notes=None)
    node_b = SimpleNamespace(confirmation_code=None, booking_notes=NOTE)
    state = {"trip_state": SimpleNamespace(nodes=[node_a, node_b])}
    assert TripStateMachine._restricted_needles(state) == [PNR, NOTE]
