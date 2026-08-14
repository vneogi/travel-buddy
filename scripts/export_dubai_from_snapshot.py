"""Build data/dubai_uae.json from a live_snapshot directory.

Used on device day. The snapshot from export_live_snapshot.py is gitignored;
this script turns the Dubai venues_rag (+ venue_dish) rows into a
loader-shaped file under data/ that can be committed and re-loaded.

A parseable file is not enough. After this script exits 0, run:

    python scripts/load_venues.py data/dubai_uae.json --dry-run

and commit only if that also exits 0.

Usage:

    set SNAP=data\\live_snapshot\\STAMP
    python scripts/export_dubai_from_snapshot.py %SNAP%

Or:

    python scripts/export_dubai_from_snapshot.py data/live_snapshot/STAMP
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "dubai_uae.json"
MIN_DUBAI = 16


def _first_local(blob, field_fallback):
    """Prefer names_local/landmarks_local JSONB; fall back to legacy TEXT."""
    if isinstance(blob, dict) and blob:
        for _lang, entry in blob.items():
            if isinstance(entry, dict) and entry.get("value"):
                return entry.get("value"), entry.get("source"), entry.get("ref")
            if isinstance(entry, str) and entry:
                return entry, None, None
    if field_fallback:
        return field_fallback, None, None
    return None, None, None


def _maybe_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def build_wrapper(venues: list, dishes: list) -> dict:
    dubai = [v for v in venues if "dubai" in (v.get("geo_region") or "")]
    if not dubai:
        raise SystemExit("ERROR: no dubai rows in venues_rag snapshot")

    by_venue: dict = {}
    for d in dishes:
        by_venue.setdefault(d.get("venue_id"), []).append(d)

    out_venues = []
    for v in sorted(dubai, key=lambda r: (r.get("name") or "")):
        names_local = _maybe_json(v.get("names_local"))
        landmarks_local = _maybe_json(v.get("landmarks_local"))
        name_local, name_src, name_ref = _first_local(names_local, v.get("name_local"))
        landmark_local, _, _ = _first_local(
            landmarks_local, v.get("nearest_landmark_local")
        )
        opening = v.get("opening_hours_structured") or v.get("opening_hours")
        opening = _maybe_json(opening) if isinstance(opening, str) else opening

        row = {
            "name": v.get("name"),
            "category": v.get("category"),
            "micro_location": v.get("micro_location"),
            "nearest_landmark": v.get("nearest_landmark"),
            "lat": v.get("lat"),
            "lng": v.get("lng"),
            "typical_dwell_minutes": v.get("typical_dwell_minutes"),
            "indoor_outdoor": v.get("indoor_outdoor"),
            "has_aircon": v.get("has_aircon"),
            "price_band": v.get("price_band"),
            "audience": v.get("audience") or [],
            "vibe_tags": v.get("vibe_tags") or [],
            "description": v.get("description") or "",
            "wheelchair_notes": v.get("wheelchair_notes"),
        }
        if name_local:
            row["name_local"] = name_local
            if name_src:
                row["name_local_source"] = name_src
            if name_ref:
                row["name_local_ref"] = name_ref
        if landmark_local:
            row["nearest_landmark_local"] = landmark_local
        if opening:
            row["opening_hours"] = opening

        attached = []
        for d in by_venue.get(v.get("venue_id"), []):
            dish = {
                k: d.get(k)
                for k in (
                    "name",
                    "name_local",
                    "dish_key",
                    "price_local",
                    "price_band",
                    "currency_code",
                    "contains",
                    "may_contain",
                    "suitable_for",
                    "description",
                )
                if d.get(k) is not None
            }
            if dish.get("name"):
                attached.append(dish)
        if attached:
            row["dishes"] = attached

        out_venues.append({k: val for k, val in row.items() if val is not None})

    return {
        "geo_region": dubai[0].get("geo_region") or "dubai_uae",
        "curated_at": date.today().isoformat(),
        "curator_notes": (
            "Exported from live Supabase on device day. Not re-curated. "
            "Preserve until a deliberate curation pass replaces it."
        ),
        "venues": out_venues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write data/dubai_uae.json from a live_snapshot directory"
    )
    parser.add_argument(
        "snapshot_dir",
        help="Path to data/live_snapshot/<stamp> from export_live_snapshot.py",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Output path (default: data/dubai_uae.json)",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=MIN_DUBAI,
        help="Hard-stop if fewer Dubai venues than this (default: 16)",
    )
    args = parser.parse_args(argv)

    snap = Path(args.snapshot_dir)
    venues_path = snap / "venues_rag.json"
    if not venues_path.is_file():
        print("ERROR: missing %s" % venues_path, file=sys.stderr)
        return 2

    venues = json.loads(venues_path.read_text(encoding="utf-8"))
    dishes_path = snap / "venue_dish.json"
    dishes = (
        json.loads(dishes_path.read_text(encoding="utf-8")) if dishes_path.is_file() else []
    )

    wrapper = build_wrapper(venues, dishes)
    count = len(wrapper["venues"])
    if count < args.min_count:
        print(
            "ERROR: expected at least %d Dubai venues, got %d -- do not commit"
            % (args.min_count, count),
            file=sys.stderr,
        )
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(wrapper, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print("wrote %s venues=%d geo_region=%s" % (out, count, wrapper["geo_region"]))
    print("NEXT: python scripts/load_venues.py %s --dry-run" % out)
    print("Commit only if that dry-run exits 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
