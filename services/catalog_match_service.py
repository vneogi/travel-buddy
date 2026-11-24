"""SPEC-58 slice 1a: deterministic catalog name match and batch plan import.

Name match: stop names plus a registered region in, catalog matches out.
No embedding, no model call, no hybrid venue search, no write, no quota.
Only ``name`` and the ``value`` strings of ``names_local`` are read.

Batch import: ``add_activity`` + ``mode=import_plan``. Each item reuses the
existing single-item checks (``apply_direct_add`` for catalog items,
``apply_uncatalogued_add`` for plain items); later items see the nodes that
earlier items added. Nothing here logs a stop name.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models.schemas import TripState
from services.day_slots import SLOT_ORDER

NAMES_MAX = 60
NAME_MIN, NAME_MAX = 2, 80
IMPORT_PLAN_MODE = "import_plan"
ITEMS_MAX = 60
NEAR_MAX = 3
PROVENANCE = "curated_catalog"

IMPORT_REFUSAL_COPY: Dict[str, str] = {
    "invalid_mode": "That import request was not recognised. Nothing was changed.",
    "invalid_items": "Send 1 to 60 complete stops to import. Nothing was changed.",
    "import_plan_refused": "None of these stops could be added. Nothing was changed.",
}


def _is_latin(ch: str) -> bool:
    return unicodedata.name(ch, "").startswith("LATIN")


def fold_name(text: str) -> str:
    """Accent-insensitive key for Latin script only.

    Latin characters are NFKD-decomposed and their combining marks dropped;
    a combining mark is dropped only when it follows a Latin base. Every
    other script (Lao, Thai, Arabic, ...) is only NFC-normalised, so its
    marks are kept and different words never merge. Then casefold and
    collapse whitespace. ``normalize_name`` is deliberately unchanged.
    """
    out: List[str] = []
    prev_latin = False
    for ch in unicodedata.normalize("NFC", text or ""):
        if unicodedata.combining(ch):
            if not prev_latin:
                out.append(ch)
            continue
        if _is_latin(ch):
            prev_latin = True
            out.extend(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        else:
            prev_latin = False
            out.append(ch)
    return " ".join("".join(out).casefold().split())


def _local_values(row: dict) -> List[str]:
    names_local = row.get("names_local")
    if not isinstance(names_local, dict):
        return []
    values = []
    for entry in names_local.values():
        value = entry.get("value") if isinstance(entry, dict) else None
        if isinstance(value, str) and value.strip():
            values.append(value)
    return values


def _shape(row: dict) -> Dict[str, Any]:
    return {
        "venue_id": row.get("venue_id"),
        "name": row.get("name"),
        "geo_region": row.get("geo_region"),
        "provenance": PROVENANCE,
    }


def _order(row: dict) -> tuple:
    return (str(row.get("name") or ""), str(row.get("venue_id") or ""))


def match_names(names: List[str], rows: List[dict]) -> List[Dict[str, Any]]:
    """Pure: one result per name, in request order."""
    indexed = [(row, fold_name(str(row.get("name") or ""))) for row in rows if row.get("venue_id")]
    indexed.sort(key=lambda pair: _order(pair[0]))
    results = []
    for name in names:
        key = fold_name(name)
        match = next((row for row, folded in indexed if folded == key), None)
        if match is None:
            match = next(
                (row for row, _ in indexed if any(fold_name(v) == key for v in _local_values(row))),
                None,
            )
        near: List[Dict[str, Any]] = []
        if match is None and key:
            tokens = set(key.split())
            for row, folded in indexed:
                row_tokens = set(folded.split())
                if row_tokens and (tokens <= row_tokens or row_tokens <= tokens):
                    near.append(_shape(row))
                if len(near) == NEAR_MAX:
                    break
        results.append(
            {"name": name, "match": _shape(match) if match is not None else None, "near": near}
        )
    return results


# ---------------------------------------------------------------------------
# Batch import (add_activity + mode=import_plan)
# ---------------------------------------------------------------------------


@dataclass
class ImportPlanOutcome:
    ok: bool
    code: str = ""
    message: str = ""
    nodes: List[Any] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)


def _valid_items(items: Any) -> bool:
    if not isinstance(items, list) or not (1 <= len(items) <= ITEMS_MAX):
        return False
    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in ("catalog", "plain"):
            return False
        required = ["target_date", "target_slot"]
        required += ["venue_id"] if item["kind"] == "catalog" else ["name"]
        if any(not isinstance(item.get(k), str) or not item[k].strip() for k in required):
            return False
        if item["kind"] == "plain" and "typical_dwell_minutes" not in item:
            return False
    return True


def _plain_folds_to_catalog(trip: TripState, item: dict, db: Any) -> bool:
    """Import-only consistency: a plain name fold-equal to a catalog name."""
    from services.direct_add_service import parse_target_date, resolve_target_region

    day = parse_target_date(item.get("target_date"))
    region = resolve_target_region(trip, day) if day is not None else None
    if not region:
        return False  # the reused add check refuses the date itself
    key = fold_name(item["name"])
    return any(
        fold_name(str(row.get("name") or "")) == key
        for row in db.list_venues_for_region(region) or []
    )


def apply_import_plan(trip: TripState, preferences: Optional[dict], db: Any) -> ImportPlanOutcome:
    """Run the existing single-item add checks per item, in day/slot order."""
    from services.direct_add_service import apply_direct_add
    from services.uncatalogued_add_service import REFUSAL_COPY as PLAIN_COPY
    from services.uncatalogued_add_service import apply_uncatalogued_add

    prefs = preferences or {}
    nodes = list(trip.nodes)
    if prefs.get("mode") != IMPORT_PLAN_MODE:
        return ImportPlanOutcome(False, "invalid_mode", IMPORT_REFUSAL_COPY["invalid_mode"], nodes)
    items = prefs.get("items")
    if not _valid_items(items):
        return ImportPlanOutcome(
            False, "invalid_items", IMPORT_REFUSAL_COPY["invalid_items"], nodes
        )

    def slot_rank(slot: str) -> int:
        return SLOT_ORDER.index(slot) if slot in SLOT_ORDER else len(SLOT_ORDER)

    order = sorted(
        range(len(items)),
        key=lambda i: (items[i]["target_date"], slot_rank(items[i]["target_slot"]), i),
    )
    current = trip
    results: Dict[int, Dict[str, Any]] = {}
    for i in order:
        item = items[i]
        if item["kind"] == "catalog":
            outcome = apply_direct_add(
                current,
                {
                    "mode": "direct_add",
                    "venue_id": item["venue_id"],
                    "target_date": item["target_date"],
                    "target_slot": item["target_slot"],
                },
                db,
            )
        elif _plain_folds_to_catalog(current, item, db):
            results[i] = {
                "index": i,
                "status": "refused",
                "node_id": None,
                "code": "catalog_match",
                "message": PLAIN_COPY["catalog_match"],
            }
            continue
        else:
            outcome = apply_uncatalogued_add(
                current,
                {
                    "mode": "uncatalogued_add",
                    "name": item["name"],
                    "target_date": item["target_date"],
                    "target_slot": item["target_slot"],
                    "typical_dwell_minutes": item["typical_dwell_minutes"],
                },
                db,
            )
        if outcome.ok:
            current = current.model_copy(update={"nodes": outcome.nodes})
            results[i] = {
                "index": i,
                "status": "added",
                "node_id": outcome.added.node_id,
                "code": None,
                "message": None,
            }
        else:
            results[i] = {
                "index": i,
                "status": "refused",
                "node_id": None,
                "code": outcome.code,
                "message": outcome.message,
            }
    ordered = [results[i] for i in range(len(items))]
    added = sum(1 for r in ordered if r["status"] == "added")
    if added == 0:
        return ImportPlanOutcome(
            False,
            "import_plan_refused",
            IMPORT_REFUSAL_COPY["import_plan_refused"],
            nodes,
            ordered,
        )
    return ImportPlanOutcome(
        True,
        "",
        f"Imported {added} of {len(items)} stops.",
        list(current.nodes),
        ordered,
    )
