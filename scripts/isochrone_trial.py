"""Isochrones trial: Haversine walk reach vs a network isochrone.

Trial harness only (docs/briefs/GENIE_ISOCHRONE_TRIAL.md, decision record
docs/decisions/NETWORK_REACHABILITY.md). For one region, one origin venue
(or lat/lng) and a walk duration it reports:

- venues Haversine says are reachable (production walking_minutes, 5 km/h);
- venues whose coordinates fall inside the isochrone (Multi)Polygon, with
  holes excluded (RFC 7946 rings: first ring exterior, the rest holes);
- the split: both, haversine_only, isochrone_only, neither.

Fixture mode reads a recorded GeoJSON file and never opens a network
socket. Live mode (--live, owner only) reads TB_GOOGLE_MAPS_API_KEY from
the environment, POSTs to the Isochrones generate endpoint, never prints
the key, and exits non-zero on any HTTP or parse failure (no silent
fallback). No product code path uses this script.

Standard library only. walking_minutes is loaded straight from
services/transit.py by file path, so the script does not import the
services package (which would load backend settings and clients).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

REPO_ROOT = Path(__file__).resolve().parent.parent

CATALOGS: Dict[str, Path] = {
    "zanzibar_tanzania": REPO_ROOT / "data" / "zanzibar_tanzania.json",
    "nungwi_tanzania": REPO_ROOT / "data" / "nungwi_tanzania.json",
    "luang_prabang_laos": REPO_ROOT / "data" / "laos_luang_prabang.json",
}

KEY_ENV = "TB_GOOGLE_MAPS_API_KEY"
# Isochrones (Preview) generate method. Verify against the current Google
# docs before the live run; --endpoint overrides it without a code change.
DEFAULT_ENDPOINT = "https://isochrones.googleapis.com/v1:generate"
DEFAULT_FIELD_MASK = "*"
LIVE_TIMEOUT_SECONDS = 30


def _load_transit():
    path = REPO_ROOT / "services" / "transit.py"
    spec = importlib.util.spec_from_file_location("_isochrone_trial_transit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


walking_minutes = _load_transit().walking_minutes


class TrialError(Exception):
    """A user-facing failure; main() prints it and exits non-zero."""


# --- catalog ----------------------------------------------------------------


def load_venues(region: str) -> List[dict]:
    """Catalog venues for *region* that have coordinates: name, lat, lng."""
    path = CATALOGS.get(region)
    if path is None:
        raise TrialError(f"unknown region {region!r}; choose one of {sorted(CATALOGS)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    venues = []
    for row in payload.get("venues", []):
        lat, lng = row.get("lat"), row.get("lng")
        if lat is None or lng is None:
            continue
        venues.append({"name": row["name"], "lat": float(lat), "lng": float(lng)})
    return venues


def find_origin(venues: Sequence[dict], name: str) -> dict:
    for venue in venues:
        if venue["name"] == name:
            return venue
    raise TrialError(f"origin venue {name!r} not found in catalog (exact name required)")


# --- geometry -----------------------------------------------------------------


def point_in_ring(lng: float, lat: float, ring: Sequence[Sequence[float]]) -> bool:
    """Even-odd ray cast. *ring* is a list of [lng, lat] positions."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_cross:
                inside = not inside
        j = i
    return inside


def point_in_polygon(lng: float, lat: float, polygon: Sequence[Sequence]) -> bool:
    """Inside the exterior ring and outside every hole."""
    if not polygon or not point_in_ring(lng, lat, polygon[0]):
        return False
    return not any(point_in_ring(lng, lat, hole) for hole in polygon[1:])


def point_in_multipolygon(lng: float, lat: float, polygons: Iterable[Sequence]) -> bool:
    return any(point_in_polygon(lng, lat, polygon) for polygon in polygons)


def polygons_from_geojson(obj) -> List[list]:
    """MultiPolygon coordinates from a geometry, Feature, FeatureCollection,
    or an Isochrones response ({"isochrone": {"geoJson": ...}})."""
    if isinstance(obj, str):
        obj = json.loads(obj)
    if not isinstance(obj, dict):
        raise TrialError("GeoJSON must be an object")
    if "isochrone" in obj:
        return polygons_from_geojson((obj["isochrone"] or {}).get("geoJson"))
    if "isochrones" in obj and obj["isochrones"]:
        return polygons_from_geojson(obj["isochrones"][0].get("geoJson"))
    kind = obj.get("type")
    if kind == "MultiPolygon":
        return list(obj["coordinates"])
    if kind == "Polygon":
        return [obj["coordinates"]]
    if kind == "Feature":
        return polygons_from_geojson(obj.get("geometry"))
    if kind == "FeatureCollection":
        out: List[list] = []
        for feature in obj.get("features", []):
            out.extend(polygons_from_geojson(feature))
        return out
    raise TrialError(f"unsupported GeoJSON type {kind!r}")


# --- comparison ---------------------------------------------------------------


def haversine_reachable(origin: dict, venues: Iterable[dict], minutes: int) -> Set[str]:
    return {
        v["name"]
        for v in venues
        if walking_minutes(origin["lat"], origin["lng"], v["lat"], v["lng"]) <= minutes
    }


def isochrone_reachable(polygons: Sequence[list], venues: Iterable[dict]) -> Set[str]:
    return {v["name"] for v in venues if point_in_multipolygon(v["lng"], v["lat"], polygons)}


def compare(haversine: Set[str], isochrone: Set[str], names: Iterable[str]) -> dict:
    all_names = set(names)
    return {
        "both": sorted(haversine & isochrone),
        "haversine_only": sorted(haversine - isochrone),
        "isochrone_only": sorted(isochrone - haversine),
        "neither": sorted(all_names - haversine - isochrone),
    }


def format_summary(region: str, origin: dict, minutes: int, source: str, result: dict) -> str:
    lines = [
        f"region={region} origin={origin['name']} ({origin['lat']}, {origin['lng']})"
        f" minutes={minutes} source={source}",
        "counts: "
        + " ".join(
            f"{k}={len(result[k])}" for k in ("both", "haversine_only", "isochrone_only", "neither")
        ),
        "haversine_only: " + (", ".join(result["haversine_only"]) or "-"),
        "isochrone_only: " + (", ".join(result["isochrone_only"]) or "-"),
    ]
    return "\n".join(lines)


# --- live ---------------------------------------------------------------------


def fetch_isochrone(
    lat: float, lng: float, minutes: int, api_key: str, endpoint: str, field_mask: str
) -> dict:
    """POST one walk isochrone request. The key goes in a header only."""
    body = {
        "origin": {"location": {"latLng": {"latitude": lat, "longitude": lng}}},
        "travelMode": "WALK",
        "travelDuration": f"{int(minutes) * 60}s",
        "travelDirection": "FROM",
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise TrialError(f"Isochrones HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TrialError(f"Isochrones request failed: {type(exc).__name__}") from None
    try:
        return json.loads(raw)
    except ValueError:
        raise TrialError("Isochrones response is not JSON") from None


# --- CLI ----------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", required=True, choices=sorted(CATALOGS))
    p.add_argument("--origin-name", help="exact catalog venue name")
    p.add_argument("--origin-lat", type=float)
    p.add_argument("--origin-lng", type=float)
    p.add_argument("--minutes", type=int, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", type=Path, help="recorded GeoJSON (offline)")
    mode.add_argument("--live", action="store_true", help=f"call Isochrones; needs {KEY_ENV}")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="live only")
    p.add_argument("--field-mask", default=DEFAULT_FIELD_MASK, help="live only")
    p.add_argument("--save-geojson", type=Path, help="live only: write the returned geometry")
    return p


def run(args: argparse.Namespace) -> str:
    if args.minutes <= 0:
        raise TrialError("--minutes must be positive")
    venues = load_venues(args.region)
    if args.origin_name:
        origin = find_origin(venues, args.origin_name)
    elif args.origin_lat is not None and args.origin_lng is not None:
        origin = {"name": "custom origin", "lat": args.origin_lat, "lng": args.origin_lng}
    else:
        raise TrialError("give --origin-name or both --origin-lat and --origin-lng")
    # The origin venue itself is not a destination.
    candidates = [v for v in venues if v["name"] != origin["name"]]

    if args.live:
        api_key = os.environ.get(KEY_ENV, "").strip()
        if not api_key:
            raise TrialError(f"--live needs {KEY_ENV} in the environment")
        response = fetch_isochrone(
            origin["lat"], origin["lng"], args.minutes, api_key, args.endpoint, args.field_mask
        )
        polygons = polygons_from_geojson(response)
        if args.save_geojson:
            feature = {
                "type": "Feature",
                "properties": {
                    "region": args.region,
                    "origin": origin["name"],
                    "minutes": args.minutes,
                    "source": "live",
                },
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            }
            args.save_geojson.write_text(json.dumps(feature, indent=1) + "\n", encoding="ascii")
        source = "live"
    else:
        polygons = polygons_from_geojson(args.fixture.read_text(encoding="utf-8"))
        source = f"fixture:{args.fixture.name}"
    if not polygons:
        raise TrialError("isochrone has no polygons")

    result = compare(
        haversine_reachable(origin, candidates, args.minutes),
        isochrone_reachable(polygons, candidates),
        [v["name"] for v in candidates],
    )
    return format_summary(args.region, origin, args.minutes, source, result)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        print(run(args))
    except TrialError as exc:
        print(f"isochrone_trial: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
