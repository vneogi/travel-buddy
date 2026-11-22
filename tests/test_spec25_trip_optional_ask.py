"""SPEC-25 trip-optional Ask (slice 1, Amendment 1), through POST /api/v1/ask.

Deterministic only. Questions are distinct per test because the Ask cache is
shared across the process (keyed on question, region and venue id).
"""

import logging

import pytest

import services.db_provider as dbp
from routers.ask_router import match_question_venue
from tests.conftest import auth

ZNZ = "zanzibar_tanzania"
LPQ = "luang_prabang_laos"
VENUE = "House of Wonders"
OTHER = "Forodhani Gardens"
EXCLUDED_KEYS = {"booking_reference", "notes", "scheduled_start", "node_id", "lat", "lng"}


def _ask(client, question, geo_region=ZNZ, user="toa-user", **extra):
    body = {"question": question, "geo_region": geo_region, **extra}
    return client.post("/api/v1/ask", headers=auth(user), json=body)


def _envelope(r):
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"ask_response"}
    return body["ask_response"]


def _names(region):
    return [v["name"] for v in dbp.db_service.list_venues_for_region(region)]


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_place_question_naming_one_venue_is_grounded(client):
    assert VENUE in _names(ZNZ)
    ask = _envelope(_ask(client, f"What is the {VENUE}?"))
    assert ask["intent"] == "place_identity"
    assert ask["path"] == "grounded_deterministic"
    assert ask["tier"] in ("assert", "hedge")
    assert VENUE in ask["answer"]
    assert ask["source_class"] == "curated_catalog"
    venue_id = next(
        v["venue_id"] for v in dbp.db_service.list_venues_for_region(ZNZ) if v["name"] == VENUE
    )
    assert ask["source_ids"] == [venue_id]


def test_question_naming_two_venues_picks_none(client):
    assert OTHER in _names(ZNZ)
    ask = _envelope(_ask(client, f"What is the {VENUE} or the {OTHER}?"))
    assert ask["tier"] in ("hedge", "refuse")
    assert ask["path"] == "retrieval_miss"
    assert ask["source_ids"] == []
    assert VENUE not in ask["answer"] and OTHER not in ask["answer"]
    # Longest wins only when one matched name contains another.
    venues = [{"name": "Forodhani"}, {"name": "Forodhani Gardens"}, {"name": "Inn"}]
    assert (
        match_question_venue("Where is Forodhani Gardens?", venues)["name"] == "Forodhani Gardens"
    )
    assert match_question_venue("Is the Inn open?", venues) is None  # under 4 characters
    assert match_question_venue("Where is the Forodhanix?", venues) is None  # whole word only


def test_place_question_naming_no_venue_misses(client):
    ask = _envelope(_ask(client, "What is that building over there?"))
    assert ask["tier"] in ("hedge", "refuse")
    assert ask["path"] == "retrieval_miss"
    assert ask["source_ids"] == []


def test_zanzibar_venue_asked_in_luang_prabang_leaks_nothing(client):
    zanzibar = _names(ZNZ)
    ask = _envelope(_ask(client, f"Tell me what the {VENUE} is.", geo_region=LPQ))
    assert ask["source_ids"] == []
    assert ask["tier"] in ("hedge", "refuse")
    for name in zanzibar:
        assert name not in ask["answer"], name


def _assert_no_trip_refusal(ask, intent):
    assert ask["intent"] == intent
    assert ask["tier"] == "refuse"
    assert ask["fallback_reason"] == "no_trip"
    assert "Start a trip" in ask["answer"]
    assert ask["proposal"] is None
    assert ask["source_ids"] == []


def test_plan_change_without_trip_is_refused_with_start_offer(client):
    ask = _envelope(_ask(client, "Can you swap my next activity for something else?"))
    _assert_no_trip_refusal(ask, "plan_change")


def test_today_tonight_without_trip_is_refused(client):
    ask = _envelope(_ask(client, "What do I have tonight?"))
    _assert_no_trip_refusal(ask, "today_tonight")


def test_current_next_without_trip_is_refused(client):
    ask = _envelope(_ask(client, "What's next?"))
    _assert_no_trip_refusal(ask, "trip_current_next")


def test_trip_id_is_refused_use_trip_event(client):
    r = _ask(client, f"What is the {VENUE} today?", trip_id="some-trip")
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "use_trip_event"


@pytest.mark.parametrize(
    "body",
    [
        {"geo_region": ZNZ},
        {"question": "", "geo_region": ZNZ},
        {"question": "   ", "geo_region": ZNZ},
        {"question": "x" * 501, "geo_region": ZNZ},
        {"question": "What is it?", "geo_region": ZNZ, "venue_name": VENUE},
        {"question": "What is it?", "geo_region": "laos_luang_prabang"},
        {"question": "What is it?"},
    ],
)
def test_invalid_request_is_422(client, body):
    r = client.post("/api/v1/ask", headers=auth("toa-422"), json=body)
    assert r.status_code == 422, r.text


def test_retrieval_miss_hedges_and_writes_nothing(client, monkeypatch):
    def _no_write(*args, **kwargs):
        raise AssertionError("catalog write attempted")

    monkeypatch.setattr(dbp.db_service, "add_venue", _no_write)
    before = len(dbp.db_service.list_venues_for_region(ZNZ))
    ask = _envelope(_ask(client, "What time does that place over there open?"))
    assert ask["tier"] in ("hedge", "refuse")
    assert ask["tier"] != "assert"
    assert len(dbp.db_service.list_venues_for_region(ZNZ)) == before


def test_repeated_question_is_a_cache_hit(client):
    question = f"Describe the {VENUE} for me, please."
    first = _envelope(_ask(client, question))
    assert first["path"] == "grounded_deterministic"
    second = _envelope(_ask(client, question))
    assert second["path"] == "cache_hit"
    assert second["from_cache"] is True
    assert second["source_ids"] == first["source_ids"]


def test_telemetry_has_intent_and_path_but_no_question_text(client, caplog):
    secret = "qx7canary"
    with caplog.at_level(logging.INFO):
        _envelope(_ask(client, f"What is the {VENUE} {secret}?"))
        _envelope(_ask(client, f"What's next {secret}?"))
    records = [r for r in caplog.records if r.getMessage() == "ask_telemetry"]
    assert {(r.intent, r.path) for r in records} >= {
        ("place_identity", "grounded_deterministic"),
        ("trip_current_next", "retrieval_miss"),
    }
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in str(record.__dict__)


def test_response_carries_no_excluded_keys(client):
    for question in (
        f"What is the {VENUE} building?",
        "Can you cancel my lunch?",
        "Where can I eat nearby?",
    ):
        body = _ask(client, question)
        assert body.status_code == 200, body.text
        assert not (set(_keys(body.json())) & EXCLUDED_KEYS), question


def test_no_model_client_is_called(client, monkeypatch):
    import litellm

    def _boom(*args, **kwargs):
        raise AssertionError("model call attempted")

    monkeypatch.setattr(litellm, "completion", _boom)
    monkeypatch.setattr(litellm, "acompletion", _boom)
    from services import llm_service as llm_module

    for name in dir(llm_module.LLMService):
        if name.startswith("generate") or name in ("complete", "acomplete"):
            monkeypatch.setattr(llm_module.LLMService, name, _boom)
    for question in (
        f"What is the {VENUE} exactly?",
        "Is there a market nearby?",
        "What's next for me?",
    ):
        assert _ask(client, question).status_code == 200


def test_trip_event_ask_info_route_unchanged(client):
    created = client.post(
        "/api/v1/trip/create",
        headers=auth("toa-trip"),
        json={"geo_region": ZNZ, "start_date": "2026-12-25", "end_date": "2026-12-26"},
    )
    assert created.status_code == 200, created.text
    r = client.post(
        "/api/v1/trip/event",
        headers=auth("toa-trip"),
        json={
            "trip_id": created.json()["trip_id"],
            "event_type": "ask_info",
            "message": "What's next?",
        },
    )
    assert r.status_code == 200, r.text
    ask = r.json()["ask_response"]
    assert ask["intent"] == "trip_current_next"
    assert ask["fallback_reason"] != "no_trip"
