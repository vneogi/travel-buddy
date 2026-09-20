"""SPEC-10: deterministic catalog name-match for booking lat/lng.

Given a venue name and geo_region, look up the venue catalog for an exact
(case-insensitive, stripped) name match in the same region.  Returns the
matching venue's (lat, lng) or (None, None).

No LLM.  No geocoding API.  No network call beyond the existing catalog.
"""

from typing import Optional, Tuple


def catalog_coords_for_name(
    venue_name: str,
    geo_region: str,
    catalog_fn=None,
) -> Tuple[Optional[float], Optional[float]]:
    """Return (lat, lng) from the catalog if a name-match exists, else (None, None).

    *catalog_fn* is a callable(geo_region) -> list[dict] that returns the
    venue catalog for the region.  Each dict must have 'name' (or
    'venue_name') plus 'lat' and 'lng'.  When None, uses
    db_service.list_venues_for_region.
    """
    if catalog_fn is None:
        from services.db_provider import db_service

        catalog_fn = db_service.list_venues_for_region

    target = venue_name.strip().lower()
    if not target:
        return None, None

    try:
        venues = catalog_fn(geo_region)
    except Exception:
        return None, None

    for v in venues:
        # Catalog dicts may use 'name' (VenueRAG) or 'venue_name'.
        raw_name = v.get("name") or v.get("venue_name") or ""
        name = raw_name.strip().lower()
        if name == target:
            lat = v.get("lat")
            lng = v.get("lng")
            if lat is not None and lng is not None:
                return float(lat), float(lng)
    return None, None
