"""Point-in-polygon for GeoJSON (Multi)Polygons in [lng, lat] order.

Production copy of the geometry in scripts/isochrone_trial.py (not imported
from it). RFC 7946 rings: the first ring of a polygon is the exterior, later
rings are holes. Even-odd ray casting. Pure functions, stdlib only, no I/O.
"""

from __future__ import annotations

import json
from typing import Iterable, List, Sequence


class GeoJSONError(ValueError):
    """The object is not a supported GeoJSON polygon shape."""


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
    """MultiPolygon coordinates from an Isochrones response
    ({"isochrone": {"geoJson": ...}}), a MultiPolygon / Polygon geometry, a
    Feature, or a FeatureCollection. geoJson may be an object or a JSON
    string. Raises GeoJSONError for anything else."""
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except ValueError:
            raise GeoJSONError("geojson is not valid JSON") from None
    if not isinstance(obj, dict):
        raise GeoJSONError("geojson must be an object")
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
    raise GeoJSONError("unsupported geojson type")
