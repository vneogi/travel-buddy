"""SPEC-58 slice 1a: POST /api/v1/trip/catalog_match (deterministic, read-only)."""

import logging

import pytest

import services.db_provider as dbp
from tests.conftest import auth

GEO = "zanzibar_tanzania"


def _seed(monkeypatch, *rows):
    """Setup only: add venues to the in-memory catalog for this test."""
    monkeypatch.setattr(dbp.db_service, "_venues", list(dbp.db_service._venues) + list(rows))


def _row(venue_id, name, names_local=None):
    return {
        "venue_id": venue_id,
        "name": name,
        "geo_region": GEO,
        "names_local": names_local,
        "category": "experience",
        "typical_dwell_minutes": 60,
    }


def _match(client, names, geo=GEO, user="cm-user"):
    return client.post(
        "/api/v1/trip/catalog_match", headers=auth(user), json={"geo_region": geo, "names": names}
    )


def _results(r):
    assert r.status_code == 200, r.text
    return r.json()["results"]


def test_exact_name_matches_ignoring_case_accents_and_spaces(client, monkeypatch):
    _seed(monkeypatch, _row("znz-test-cafe-sunrise", "Caf\u00e9 Sunrise Test"))
    house = next(
        v for v in dbp.db_service.list_venues_for_region(GEO) if v["name"] == "House of Wonders"
    )
    res = _results(_match(client, ["  house OF   wonders ", "CAFE  sunrise test"]))
    assert res[0]["name"] == "house OF   wonders"
    assert res[0]["match"]["venue_id"] == house["venue_id"]
    assert res[0]["match"]["provenance"] == "curated_catalog"
    assert res[0]["match"]["geo_region"] == GEO
    assert res[1]["match"]["venue_id"] == "znz-test-cafe-sunrise"
    assert res[0]["near"] == [] and res[1]["near"] == []


def test_local_name_alias_matches(client, monkeypatch):
    _seed(
        monkeypatch,
        _row(
            "znz-test-alias",
            "Wonder Hall Test",
            {"sw": {"value": "Nyumba ya Maajabu Test", "source": "curated"}},
        ),
    )
    res = _results(_match(client, ["nyumba ya maajabu test"]))
    assert res[0]["match"]["venue_id"] == "znz-test-alias"


def test_token_subset_names_are_near_in_stable_order(client):
    res = _results(_match(client, ["Forodhani"]))
    assert res[0]["match"] is None
    names = [v["name"] for v in res[0]["near"]]
    assert names == sorted(names)
    assert 1 <= len(names) <= 3
    assert all("forodhani" in n.lower() for n in names)
    again = _results(_match(client, ["Forodhani"]))
    assert again == res


def test_unknown_name_returns_no_match_and_no_near(client):
    res = _results(_match(client, ["Zzqx Nowhere Place"]))
    assert res == [{"name": "Zzqx Nowhere Place", "match": None, "near": []}]


def test_no_embedding_model_or_hybrid_search_is_called(client, monkeypatch):
    import litellm

    import importlib

    emb = importlib.import_module("services.embedding_service")
    from services import llm_service as llm_module

    calls = {"embed": 0, "hybrid": 0, "llm": 0}

    def _count(key):
        def inner(*args, **kwargs):
            calls[key] += 1
            raise AssertionError(key)

        return inner

    monkeypatch.setattr(emb.embedding_service, "generate_embedding", _count("embed"))
    monkeypatch.setattr(dbp.db_service, "hybrid_venue_search", _count("hybrid"))
    monkeypatch.setattr(litellm, "completion", _count("llm"))
    monkeypatch.setattr(litellm, "acompletion", _count("llm"))
    for name in dir(llm_module.LLMService):
        if name.startswith("generate") or name in ("complete", "acomplete"):
            monkeypatch.setattr(llm_module.LLMService, name, _count("llm"))
    res = _results(_match(client, ["House of Wonders", "Forodhani", "Nowhere Place"]))
    assert len(res) == 3
    assert calls == {"embed": 0, "hybrid": 0, "llm": 0}


def test_no_quota_used_and_no_event_written(client, monkeypatch):
    events = []
    monkeypatch.setattr(dbp.db_service, "log_event", lambda **kw: events.append(kw))
    before = client.get("/api/v1/user/status", headers=auth("cm-quota")).json()
    _results(_match(client, ["House of Wonders"], user="cm-quota"))
    assert client.get("/api/v1/user/status", headers=auth("cm-quota")).json() == before
    assert events == []


@pytest.mark.parametrize(
    "body",
    [
        {"geo_region": "atlantis", "names": ["House of Wonders"]},
        {"geo_region": GEO, "names": []},
        {"geo_region": GEO, "names": [f"Place {i}" for i in range(61)]},
        {"geo_region": GEO, "names": ["x"]},
        {"geo_region": GEO, "names": ["House of Wonders"], "raw": "pasted text"},
    ],
)
def test_bad_requests_are_refused_before_any_lookup(client, monkeypatch, body):
    reads = []
    real = dbp.db_service.list_venues_for_region
    monkeypatch.setattr(
        dbp.db_service, "list_venues_for_region", lambda g: reads.append(g) or real(g)
    )
    r = client.post("/api/v1/trip/catalog_match", headers=auth("cm-422"), json=body)
    assert r.status_code == 422, r.text
    assert reads == []


def test_request_names_never_appear_in_logs(client, caplog):
    secret = "Qx7 Secret Jetty"
    with caplog.at_level(logging.DEBUG):
        _results(_match(client, [secret, "House of Wonders"]))
    for record in caplog.records:
        assert secret.lower() not in record.getMessage().lower()
        assert secret.lower() not in str(record.__dict__).lower()


def test_accent_folding_is_latin_only_and_normalize_name_unchanged(client, monkeypatch):
    from services.uncatalogued_add_service import normalize_name

    lao = "\u0ea7\u0eb1\u0e94\u0e97\u0eb2\u0e94"  # with a combining vowel mark
    lao_without_mark = "\u0ea7\u0e94\u0e97\u0eb2\u0e94"
    _seed(
        monkeypatch,
        _row("znz-test-lumiere", "Caf\u00e9 Lumi\u00e8re Test"),
        _row("znz-test-lao", "Temple Row Test", {"lo": {"value": lao, "source": "curated"}}),
    )
    res = _results(_match(client, ["cafe lumiere test", lao, lao_without_mark]))
    assert res[0]["match"]["venue_id"] == "znz-test-lumiere"
    assert res[1]["match"]["venue_id"] == "znz-test-lao"
    assert res[2]["match"] is None and res[2]["near"] == []
    assert normalize_name("  Caf\u00e9   Lumi\u00e8re ") == "caf\u00e9 lumi\u00e8re"
    assert normalize_name("House  of Wonders") == "house of wonders"
