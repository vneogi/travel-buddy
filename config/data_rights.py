"""SPEC-43 Gap 4 slice 1: data-rights inventory and schema-walk guard.

Every table created by supabase/migrations/*.sql must have an explicit rights
classification in RIGHTS_MAP. A new table that carries an identity column
fails tests/test_spec43_g4_rights_inventory.py until it is classified here.

Slice 1 is inventory only: no export, deletion, tombstone or retention job
exists yet, so export and delete are "planned" for every table.

Standard library only. ASCII only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple, Union

PathLike = Union[str, Path]

# Columns that make a table identity-bearing (shared with the tests).
IDENTITY_COLUMNS: Tuple[str, ...] = ("user_id", "party_id", "identity_id", "owner_id")

IDENTITY_VALUES = frozenset({"direct_user_id", "via_trip_states", "via_party", "none"})
SLICE_ONE_EXPORT = frozenset({"planned"})
SLICE_ONE_DELETE = frozenset({"planned"})
RETENTION_VALUES = frozenset({"planned", "not_applicable"})
RIGHTS_KEYS = frozenset({"identity", "export", "delete", "retention", "note"})

_CREATE_RE = re.compile(
    r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?(\w+)", re.IGNORECASE
)
_DROP_RE = re.compile(
    r"\bdrop\s+table\s+(?:if\s+exists\s+)?((?:(?:public\.)?\w+\s*,\s*)*(?:public\.)?\w+)",
    re.IGNORECASE,
)
_IDENTITY_RE = re.compile(r"\b(" + "|".join(IDENTITY_COLUMNS) + r")\b", re.IGNORECASE)


def strip_sql_comments(text: str) -> str:
    """Remove -- line comments and /* */ block comments.

    Single-quoted strings and $$ / $tag$ dollar-quoted bodies are copied
    through untouched so comment markers inside them are not treated as
    comments.
    """
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            if j == -1:
                break
            i = j  # keep the newline
            continue
        if ch == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            out.append(" ")
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(text[i : j + 1])
            i = j + 1
            continue
        if ch == "$":
            m = re.match(r"\$(\w*)\$", text[i:])
            if m:
                tag = m.group(0)
                j = text.find(tag, i + len(tag))
                end = n if j == -1 else j + len(tag)
                out.append(text[i:end])
                i = end
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _migration_texts(migrations_dir: PathLike) -> Iterable[Tuple[Path, str]]:
    for path in sorted(Path(migrations_dir).glob("*.sql"), key=lambda p: p.name):
        yield path, strip_sql_comments(path.read_text(encoding="utf-8"))


def _balanced_body(text: str, start: int) -> str:
    """Text inside the first balanced (...) at or after *start*."""
    open_at = text.find("(", start)
    if open_at == -1:
        return ""
    depth = 0
    for k in range(open_at, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : k]
    return text[open_at + 1 :]


def _walk(migrations_dir: PathLike) -> Dict[str, str]:
    """Live table name -> CREATE body, applying CREATE and DROP in order."""
    live: Dict[str, str] = {}
    for _path, text in _migration_texts(migrations_dir):
        events = []
        for m in _CREATE_RE.finditer(text):
            events.append(("create", m.start(), m.group(1).lower(), _balanced_body(text, m.end())))
        for m in _DROP_RE.finditer(text):
            for raw in m.group(1).split(","):
                name = raw.strip().lower()
                if name.startswith("public."):
                    name = name[len("public.") :]
                events.append(("drop", m.start(), name, ""))
        for kind, _pos, name, body in sorted(events, key=lambda e: e[1]):
            if kind == "create":
                # An "if not exists" create on a live table is a no-op.
                live.setdefault(name, body)
            else:
                live.pop(name, None)
    return live


def walk_created_tables(migrations_dir: PathLike) -> Set[str]:
    """Lowercase names of tables created and not later dropped."""
    return set(_walk(migrations_dir))


def identity_tables(migrations_dir: PathLike) -> Set[str]:
    """Created tables whose CREATE body names an IDENTITY_COLUMNS column."""
    return {name for name, body in _walk(migrations_dir).items() if _IDENTITY_RE.search(body)}


def identity_columns_in(migrations_dir: PathLike) -> Dict[str, List[str]]:
    """Table -> sorted identity column names found in its CREATE body."""
    out: Dict[str, List[str]] = {}
    for name, body in _walk(migrations_dir).items():
        cols = sorted({m.group(1).lower() for m in _IDENTITY_RE.finditer(body)})
        if cols:
            out[name] = cols
    return out


def unclassified(created: Set[str], rights: Dict[str, dict]) -> Set[str]:
    return set(created) - set(rights)


def stale(created: Set[str], rights: Dict[str, dict]) -> Set[str]:
    return set(rights) - set(created)


def _entry(identity: str, retention: str, note: str) -> dict:
    return {
        "identity": identity,
        "export": "planned",
        "delete": "planned",
        "retention": retention,
        "note": note,
    }


# One entry per table created by supabase/migrations/*.sql (Gap 4 slice 1).
# identity is derived from each table-create body and the 0026 RLS policies.
RIGHTS_MAP: Dict[str, dict] = {
    # --- Personal: direct owner column ---
    "user_tiers": _entry(
        "direct_user_id", "planned", "user_tiers.user_id is the account key (0001)."
    ),
    "trip_states": _entry(
        "direct_user_id", "planned", "trip_states.user_id owns each trip (0001); root for joins."
    ),
    "event_log": _entry("direct_user_id", "planned", "event_log.user_id per trip event (0001)."),
    "signal": _entry(
        "direct_user_id", "planned", "signal.user_id on behavioral signals (0002); trip_id too."
    ),
    "trip_command": _entry(
        "direct_user_id",
        "planned",
        "trip_command.user_id (0025); 0026 also scopes it via trip_states.trip_id.",
    ),
    # --- Personal: owner reachable only through a parent ---
    "trip_node": _entry(
        "via_trip_states",
        "planned",
        "No owner column; trip_node.trip_id joins trip_states.trip_id (0014, 0026).",
    ),
    "trip_edge": _entry(
        "via_trip_states",
        "planned",
        "No owner column; trip_edge.trip_id joins trip_states.trip_id (0014, 0026).",
    ),
    "trip_party": _entry(
        "via_trip_states",
        "planned",
        "party_id is its own key; trip_party.trip_id (text) joins trip_states.trip_id::text.",
    ),
    "party_member": _entry(
        "via_party",
        "planned",
        "party_member.party_id joins trip_party, then trip_party.trip_id joins trip_states.",
    ),
    # --- Personal content without an owner column ---
    "cached_responses": _entry(
        "none",
        "planned",
        "No owner column (0026 denies authenticated); holds query_text and responses.",
    ),
    # --- Catalog / reference: no traveller identity ---
    "venues_rag": _entry("none", "not_applicable", "Venue catalog; no traveller column."),
    "venue_dish": _entry("none", "not_applicable", "Dish catalog keyed by venue_id; no traveller."),
    "signal_type": _entry("none", "not_applicable", "Signal type registry; no traveller column."),
    "source": _entry("none", "not_applicable", "Data source registry; no traveller column."),
    "taxonomy_term": _entry("none", "not_applicable", "Controlled vocabulary; no traveller."),
    "dish_glossary": _entry("none", "not_applicable", "Dish glossary; no traveller column."),
    "venue_external_id": _entry(
        "none", "not_applicable", "Venue id crosswalk to providers; no traveller column."
    ),
}
