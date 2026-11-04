"""SPEC-43 Gap 3: booking fields never reach the heavy itinerary LLM payload.

Goes through LLMService.generate_itinerary_response (R17). No network: the
completion call is replaced by a capture double.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from services.llm_service import (
    LLMService,
    public_itinerary_nodes,
    public_replacement_venues,
)

PNR = "G3-CANARY-PNR-9f3a"
NOTE = "G3-CANARY-NOTE"
LAT = 19.876543
LNG = 102.134567
USER_ID = "user-g3-canary-id-7c1d"
RESTRICTED = (
    "confirmation_code",
    "booking_notes",
    "lat",
    "lng",
    "node_id",
    "venue_id",
    "import_source",
    "names_local",
    "place_source",
)


def _trip_state():
    return {
        "trip_id": "trip-g3",
        "user_id": USER_ID,
        "nodes": [
            {
                "node_id": "node-g3-1",
                "venue_id": "venue-g3-1",
                "venue_name": "Wat Xieng Thong",
                "scheduled_start": "2026-10-07T09:00:00+07:00",
                "duration_minutes": 90,
                "is_locked": False,
                "status": "pending",
                "node_kind": "booking",
                "slot_name": "morning",
                "geo_region": "luang_prabang",
                "vibe_tags": ["temple"],
                "micro_location": "Peninsula",
                "confirmation_code": PNR,
                "booking_notes": f"Window seat for {NOTE}",
                "lat": LAT,
                "lng": LNG,
                "import_source": "email",
                "names_local": {"lo": "x"},
                "place_source": "trip_private",
            }
        ],
    }


def _venues():
    return [
        {
            "name": "Utopia",
            "micro_location": "Nam Khan",
            "vibe_tags": ["bar"],
            "lat": LAT,
            "lng": LNG,
        }
    ]


@pytest.fixture
def captured(monkeypatch):
    calls = []

    async def fake_complete(self, messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        return {"content": "ok", "model_used": "fake", "tokens": {}, "cost_usd": 0.0}

    monkeypatch.setattr(LLMService, "complete", fake_complete)
    return calls


def _run(svc, user_id=USER_ID):
    return asyncio.run(
        svc.generate_itinerary_response(
            user_message="Swap the afternoon stop.",
            trip_state=_trip_state(),
            venues_found=_venues(),
            routing_tier="heavy",
            context={"geo_region": "luang_prabang"},
            user_id=user_id,
        )
    )


def test_itinerary_llm_payload_omits_booking_canary(captured):
    assert _run(LLMService()) == "ok"
    assert len(captured) == 1
    dumped = json.dumps(captured[0]["messages"])
    assert PNR not in dumped
    assert NOTE not in dumped
    assert str(LAT) not in dumped
    assert str(LNG) not in dumped
    assert "Wat Xieng Thong" in dumped


def test_user_id_is_spend_identity_not_prompt_text(captured):
    _run(LLMService())
    assert captured[0]["user_id"] == USER_ID
    assert USER_ID not in json.dumps(captured[0]["messages"])


def test_real_complete_sends_no_canary_to_litellm(monkeypatch):
    # Through the real complete(): capture what litellm.acompletion receives.
    import litellm

    sent = []

    async def fake_acompletion(**kwargs):
        sent.append(kwargs)
        usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        msg = SimpleNamespace(content="ok")
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    assert _run(LLMService()) == "ok"
    assert sent
    dumped = json.dumps(sent[0]["messages"])
    for canary in (PNR, NOTE, str(LAT), str(LNG), USER_ID):
        assert canary not in dumped
    assert "Wat Xieng Thong" in dumped


def test_public_itinerary_nodes_drops_restricted_keys():
    out = public_itinerary_nodes(_trip_state()["nodes"] + ["not-a-dict", None])
    assert len(out) == 1
    node = out[0]
    for key in RESTRICTED:
        assert key not in node
    assert node["venue_name"] == "Wat Xieng Thong"
    assert node["scheduled_start"] == "2026-10-07T09:00:00+07:00"
    assert set(node) == {
        "venue_name",
        "scheduled_start",
        "duration_minutes",
        "is_locked",
        "status",
        "node_kind",
        "slot_name",
        "geo_region",
        "vibe_tags",
        "micro_location",
    }


def test_public_replacement_venues_drops_coordinates():
    out = public_replacement_venues(_venues() + [42])
    assert out == [{"name": "Utopia", "micro_location": "Nam Khan", "vibe_tags": ["bar"]}]


def test_secret_in_allowed_field_is_redacted(captured):
    trip = _trip_state()
    trip["nodes"][0]["micro_location"] = "near https://x.test/?key=AIzaG3CanaryKey000"
    asyncio.run(
        LLMService().generate_itinerary_response(
            user_message="Swap the afternoon stop.",
            trip_state=trip,
            venues_found=[],
            user_id=USER_ID,
        )
    )
    assert "AIzaG3CanaryKey000" not in json.dumps(captured[0]["messages"])
