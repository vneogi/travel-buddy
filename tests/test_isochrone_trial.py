"""Isochrones trial harness (scripts/isochrone_trial.py): offline logic proof.

No network: fixture mode is checked with sockets disabled, and live mode is
only exercised for its missing-key failure.
"""

import json
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import isochrone_trial as trial  # noqa: E402
from services.transit import walking_minutes as production_walking_minutes  # noqa: E402

FIXTURES = REPO_ROOT / "data" / "isochrone_fixtures"


def _square(w, s, e, n):
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def test_point_in_polygon_respects_hole():
    polygon = [_square(0.0, 0.0, 10.0, 10.0), list(reversed(_square(4.0, 4.0, 6.0, 6.0)))]
    assert trial.point_in_polygon(1.0, 1.0, polygon) is True
    assert trial.point_in_polygon(5.0, 5.0, polygon) is False  # inside the hole
    assert trial.point_in_polygon(11.0, 5.0, polygon) is False  # outside
    assert trial.point_in_multipolygon(5.0, 5.0, [polygon]) is False
    # A second polygon covering the hole makes the point reachable again.
    assert trial.point_in_multipolygon(5.0, 5.0, [polygon, [_square(4.5, 4.5, 5.5, 5.5)]])
    # Real fixture: the Old Slave Market sits in the Stone Town 30m hole.
    polygons = trial.polygons_from_geojson((FIXTURES / "zanzibar_30m.geojson").read_text())
    assert trial.point_in_multipolygon(39.1925, -6.16337, polygons) is False
    assert trial.point_in_multipolygon(39.18905, -6.16136, polygons) is True  # Old Fort


def test_haversine_set_matches_walking_minutes():
    assert trial.walking_minutes(-6.16, 39.18, -6.17, 39.19) == production_walking_minutes(
        -6.16, 39.18, -6.17, 39.19
    )
    for region in trial.CATALOGS:
        venues = trial.load_venues(region)
        assert venues, region
        origin = venues[0]
        for minutes in (15, 30, 45):
            expected = {
                v["name"]
                for v in venues
                if production_walking_minutes(origin["lat"], origin["lng"], v["lat"], v["lng"])
                <= minutes
            }
            assert trial.haversine_reachable(origin, venues, minutes) == expected


def test_fixture_mode_reports_symmetric_difference(tmp_path, capsys):
    # Synthetic: one venue in both sets, one only by Haversine, one only by area.
    origin = {"name": "O", "lat": 0.0, "lng": 0.0}
    venues = [
        {"name": "near_in", "lat": 0.0, "lng": 0.005},
        {"name": "near_out", "lat": 0.0, "lng": -0.005},
        {"name": "far_in", "lat": 0.0, "lng": 0.05},
        {"name": "far_out", "lat": 0.0, "lng": -0.05},
    ]
    polygons = [[_square(0.001, -0.01, 0.06, 0.01)]]
    result = trial.compare(
        trial.haversine_reachable(origin, venues, 15),
        trial.isochrone_reachable(polygons, venues),
        [v["name"] for v in venues],
    )
    assert result == {
        "both": ["near_in"],
        "haversine_only": ["near_out"],
        "isochrone_only": ["far_in"],
        "neither": ["far_out"],
    }
    # Real catalog through the CLI: the split partitions every non-origin venue.
    code = trial.main(
        [
            "--region",
            "zanzibar_tanzania",
            "--origin-name",
            "House of Wonders",
            "--minutes",
            "30",
            "--fixture",
            str(FIXTURES / "zanzibar_30m.geojson"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    counts = dict(part.split("=") for part in out.splitlines()[1].removeprefix("counts: ").split())
    total = len(trial.load_venues("zanzibar_tanzania")) - 1  # origin excluded
    assert sum(int(v) for v in counts.values()) == total
    assert "Old Slave Market and Slavery Memorial" in out.splitlines()[2]
    assert "source=fixture:zanzibar_30m.geojson" in out


def test_live_flag_without_key_exits_nonzero(monkeypatch, capsys):
    monkeypatch.delenv(trial.KEY_ENV, raising=False)
    called = []
    monkeypatch.setattr(trial, "fetch_isochrone", lambda *a, **k: called.append(a))
    code = trial.main(
        [
            "--region",
            "nungwi_tanzania",
            "--origin-name",
            "Nungwi Lighthouse",
            "--minutes",
            "15",
            "--live",
        ]
    )
    err = capsys.readouterr().err
    assert code != 0
    assert trial.KEY_ENV in err
    assert called == []


def test_fixture_mode_does_not_open_network(monkeypatch, capsys):
    attempts = []

    def _blocked(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("network access attempted in fixture mode")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setenv(trial.KEY_ENV, "not-a-real-key-fixture-test")
    for fixture, region, origin, minutes in (
        ("zanzibar_15m.geojson", "zanzibar_tanzania", "House of Wonders", "15"),
        ("nungwi_30m.geojson", "nungwi_tanzania", "Nungwi Lighthouse", "30"),
        ("luang_prabang_30m.geojson", "luang_prabang_laos", "Royal Palace Museum (Haw Kham)", "30"),
    ):
        code = trial.main(
            [
                "--region",
                region,
                "--origin-name",
                origin,
                "--minutes",
                minutes,
                "--fixture",
                str(FIXTURES / fixture),
            ]
        )
        assert code == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert attempts == []
    assert "not-a-real-key-fixture-test" not in out


def test_touched_files_are_ascii():
    paths = [
        REPO_ROOT / "scripts" / "isochrone_trial.py",
        Path(__file__),
        REPO_ROOT / "docs" / "briefs" / "ISOCHRONE_TRIAL_OWNER_RUN.md",
        *sorted(FIXTURES.iterdir()),
    ]
    assert len(paths) >= 9
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert text.isascii(), path.name
        if path.suffix == ".geojson":
            feature = json.loads(text)
            assert feature["geometry"]["type"] == "MultiPolygon"
            assert "key" not in json.dumps(feature).lower()
