"""SPEC-43 Gap 4 slice 18: nested export document builder (pure function).

Realistic input comes from InMemoryExportBackend + execute_export with the
two-user seed (copied from tests/test_spec43_g4_export_memory.py, not
imported). Edge cases use small hand-built inputs. No SQL, no network.
"""

import copy
import json
import uuid
from pathlib import Path

import pytest

import services.data_rights_export_document as doc_module
from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS, execute_export
from services.data_rights_export_document import build_export_document, count_rows
from services.data_rights_export_memory import InMemoryExportBackend

USER_A = "user-g4-doc-A"
USER_B = "user-g4-doc-B"
UNATTACHED_KEYS = {
    "trip_node",
    "trip_edge",
    "trip_party",
    "party_member",
    "trip_command",
    "signal",
    "event_log",
}


def _seed_user(backend, user_id, trips=2):
    backend.seed("user_tiers", {"user_id": user_id, "seed_owner": user_id})
    for t in range(trips):
        trip_id = uuid.uuid4()
        party_id = f"party-{user_id}-{t}"
        backend.seed("trip_states", {"user_id": user_id, "trip_id": trip_id, "seed_owner": user_id})
        for table in ("event_log", "signal", "trip_command"):
            backend.seed(table, {"user_id": user_id, "trip_id": trip_id, "seed_owner": user_id})
        for n in range(2):
            backend.seed("trip_node", {"trip_id": trip_id, "seq": n, "seed_owner": user_id})
        backend.seed("trip_edge", {"trip_id": trip_id, "seed_owner": user_id})
        # trip_party.trip_id is text in the schema.
        backend.seed(
            "trip_party", {"trip_id": str(trip_id), "party_id": party_id, "seed_owner": user_id}
        )
        for role in ("lead", "companion"):
            backend.seed(
                "party_member", {"party_id": party_id, "role": role, "seed_owner": user_id}
            )


def _input_counts(results):
    return {r["table"]: len(r["rows"]) for r in results}


def _empty_results(**rows):
    return [{"table": t, "rows": list(rows.get(t, []))} for t in sorted(EXPORT_REQUIRED)]


def _doc_rows(document):
    """Every row in the document, keyed by source table (walks the document)."""
    out = {t: [] for t in EXPORT_REQUIRED}
    out["user_tiers"] += document["account"]["user_tiers"]
    for trip in document["trips"]:
        out["trip_states"].append(trip["trip"])
        out["trip_node"] += trip["nodes"]
        out["trip_edge"] += trip["edges"]
        out["trip_command"] += trip["commands"]
        out["signal"] += trip["signals"]
        out["event_log"] += trip["events"]
        for party in trip["parties"]:
            out["trip_party"].append(party["party"])
            out["party_member"] += party["members"]
    for table, rows in document["unattached"].items():
        out[table] += rows
    return out


def _sorted_reprs(rows):
    return sorted(repr(sorted(r.items(), key=lambda kv: kv[0])) for r in rows)


@pytest.fixture
def results():
    backend = InMemoryExportBackend()
    _seed_user(backend, USER_A)
    _seed_user(backend, USER_B)
    return execute_export(USER_A, backend)


def test_document_conserves_every_exported_row(results):
    document = build_export_document(results)
    assert count_rows(document) == _input_counts(results)
    rows = _doc_rows(document)
    for entry in results:
        assert _sorted_reprs(rows[entry["table"]]) == _sorted_reprs(entry["rows"]), entry["table"]


def test_trip_children_nest_under_their_trip(results):
    document = build_export_document(results)
    trips_in = next(r["rows"] for r in results if r["table"] == "trip_states")
    assert len(document["trips"]) == len(trips_in) > 0
    for trip in document["trips"]:
        key = str(trip["trip"]["trip_id"])
        for doc_key in ("nodes", "edges", "commands", "signals", "events"):
            assert trip[doc_key], doc_key
            assert all(str(r["trip_id"]) == key for r in trip[doc_key]), doc_key
    assert set(document["unattached"]) == UNATTACHED_KEYS
    assert all(rows == [] for rows in document["unattached"].values())


def test_party_members_nest_under_their_party(results):
    document = build_export_document(results)
    for trip in document["trips"]:
        assert trip["parties"]
        for party in trip["parties"]:
            assert str(party["party"]["trip_id"]) == str(trip["trip"]["trip_id"])
            assert party["members"]
            assert all(
                str(m["party_id"]) == str(party["party"]["party_id"]) for m in party["members"]
            )


def test_text_and_uuid_trip_ids_match():
    trip_id = uuid.uuid4()
    inp = _empty_results(
        trip_states=[{"trip_id": trip_id}],
        trip_party=[{"trip_id": str(trip_id), "party_id": "p-1"}],
        party_member=[{"party_id": "p-1", "role": "lead"}],
        trip_node=[{"trip_id": str(trip_id), "seq": 0}],
    )
    document = build_export_document(inp)
    trip = document["trips"][0]
    assert trip["parties"] == [
        {
            "party": {"trip_id": str(trip_id), "party_id": "p-1"},
            "members": [{"party_id": "p-1", "role": "lead"}],
        }
    ]
    assert trip["nodes"] == [{"trip_id": str(trip_id), "seq": 0}]
    assert document["unattached"]["trip_party"] == []
    assert document["unattached"]["trip_node"] == []


def test_orphan_rows_go_to_unattached_not_dropped():
    trip_id = uuid.uuid4()
    inp = _empty_results(
        trip_states=[{"trip_id": trip_id}],
        signal=[{"trip_id": None, "kind": "orphan-signal"}],
        event_log=[{"trip_id": str(uuid.uuid4()), "kind": "orphan-event"}],
        trip_node=[{"trip_id": "no-such-trip", "seq": 9}, {"seq": 10}],
        trip_party=[{"trip_id": "no-such-trip", "party_id": "p-orphan"}],
        party_member=[
            {"party_id": "p-not-exported", "role": "lead"},
            {"party_id": "p-orphan", "role": "companion"},
        ],
    )
    document = build_export_document(inp)
    un = document["unattached"]
    assert un["signal"] == [{"trip_id": None, "kind": "orphan-signal"}]
    assert [r["kind"] for r in un["event_log"]] == ["orphan-event"]
    assert un["trip_node"] == [{"trip_id": "no-such-trip", "seq": 9}, {"seq": 10}]
    assert un["trip_party"] == [{"trip_id": "no-such-trip", "party_id": "p-orphan"}]
    assert [m["party_id"] for m in un["party_member"]] == ["p-not-exported", "p-orphan"]
    assert document["trips"][0]["signals"] == [] and document["trips"][0]["parties"] == []
    assert count_rows(document) == _input_counts(inp)


def test_document_contains_only_the_callers_rows(results):
    document = build_export_document(results)
    rows = _doc_rows(document)
    assert all(r.get("seed_owner") == USER_A for table_rows in rows.values() for r in table_rows)
    dumped = json.dumps(document, default=str)
    assert USER_B not in dumped
    assert USER_A in dumped


def test_input_is_not_mutated_and_output_does_not_alias(results):
    before = copy.deepcopy(results)
    document = build_export_document(results)
    assert results == before
    document["account"]["user_tiers"][0]["seed_owner"] = "mutated"
    document["trips"][0]["trip"]["seed_owner"] = "mutated"
    document["trips"][0]["parties"][0]["members"][0]["role"] = "mutated"
    document["trips"][0]["nodes"].append({"injected": True})
    assert results == before


def test_rejects_missing_unknown_or_duplicate_tables(results):
    missing = [r for r in results if r["table"] != "signal"]
    extra = list(results) + [{"table": "cached_responses", "rows": []}]
    dup = list(results) + [next(r for r in results if r["table"] == "trip_node")]
    bad_rows = [dict(r, rows="not-a-list") if r["table"] == "event_log" else r for r in results]
    for case in (missing, extra, dup, bad_rows):
        with pytest.raises(ValueError) as excinfo:
            build_export_document(case)
        assert USER_A not in str(excinfo.value) and USER_B not in str(excinfo.value)


def test_rejects_duplicate_trip_or_party_keys():
    trip_id = uuid.uuid4()
    with pytest.raises(ValueError):
        build_export_document(
            _empty_results(trip_states=[{"trip_id": trip_id}, {"trip_id": str(trip_id)}])
        )
    with pytest.raises(ValueError):
        build_export_document(
            _empty_results(
                trip_states=[{"trip_id": trip_id}],
                trip_party=[
                    {"trip_id": str(trip_id), "party_id": "p-dup"},
                    {"trip_id": str(trip_id), "party_id": "p-dup"},
                ],
            )
        )


def test_empty_export_has_every_key():
    document = build_export_document(_empty_results())
    assert set(document) == {"format", "version", "account", "trips", "unattached"}
    assert document["format"] == "travel-buddy-export"
    assert document["version"] == 1
    assert document["account"] == {"user_tiers": []}
    assert document["trips"] == []
    assert set(document["unattached"]) == UNATTACHED_KEYS
    assert all(rows == [] for rows in document["unattached"].values())
    assert count_rows(document) == {t: 0 for t in EXPORT_REQUIRED}


def test_accepts_http_shape_without_method_and_via(results):
    assert {"method", "via"} <= set(results[0])
    http_shape = [{"table": r["table"], "rows": r["rows"]} for r in results]
    assert build_export_document(http_shape) == build_export_document(results)
    assert [r["table"] for r in results] == [s["table"] for s in EXPORT_STEPS]


def test_export_document_module_is_ascii():
    source = Path(doc_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    assert "import logging" not in source
    assert "print(" not in source
