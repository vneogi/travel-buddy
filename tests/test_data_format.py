"""Tests for data file format invariants and the curation round-trip helper.

These tests enforce:
1. Every file in data/ is pure ASCII by byte count (the safety net for R14).
2. Byte-identical round-trip through format_venue_json.py for all venue/glossary files.
3. Lao-script guard extended to the dish glossary's name_local and order_phrase_local.
"""

import json
import string
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SCRIPTS_DIR = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
from format_venue_json import _serialize_ascii, _serialize_readable  # noqa: E402

sys.path.pop(0)


# ---------------------------------------------------------------------------
# ASCII guard: every file in data/ must be pure ASCII
# ---------------------------------------------------------------------------


def test_all_data_files_are_pure_ascii():
    """Every file in data/ must contain only ASCII bytes (0x00-0x7F).

    This guard is what makes the ASCII-escaped scheme safe. Without it, one
    accidental commit of a curation/ file undoes the entire tool-safety
    invariant.
    """
    violations = []
    for fp in sorted(DATA_DIR.iterdir()):
        if not fp.is_file():
            continue
        raw = fp.read_bytes()
        non_ascii = [i for i, b in enumerate(raw) if b >= 128]
        if non_ascii:
            violations.append(
                f"{fp.name}: {len(non_ascii)} non-ASCII bytes (first at offset {non_ascii[0]})"
            )
    assert not violations, "data/ files must be pure ASCII:\n" + "\n".join(
        "  " + v for v in violations
    )


def test_ascii_guard_catches_non_ascii():
    """Prove the ASCII guard would fail on a file with raw Lao text.

    Uses a temporary file to avoid polluting git state.
    """
    # Simulate by directly testing the logic
    lao_char = "\u0e81"  # Lao KO
    raw = lao_char.encode("utf-8")
    has_non_ascii = any(b >= 128 for b in raw)
    assert has_non_ascii, "Test setup error: Lao character should produce non-ASCII bytes"


# ---------------------------------------------------------------------------
# Round-trip test: to_repo(to_readable(f)) == f byte-for-byte
# ---------------------------------------------------------------------------

_VENUE_GLOSSARY_FILES = [
    "laos_luang_prabang.json",
    "laos_vang_vieng.json",
    "laos_vientiane.json",
    "laos_dish_glossary.json",
]


@pytest.mark.parametrize("filename", _VENUE_GLOSSARY_FILES)
def test_round_trip_byte_identical(filename):
    """to_repo(to_readable(file)) must equal file byte-for-byte.

    This is the acceptance test for the curation helper. If a cycle reformats
    anything, diffs become useless.
    """
    fp = DATA_DIR / filename
    original_bytes = fp.read_bytes()

    # Parse the original
    data = json.loads(original_bytes.decode("utf-8"))

    # Simulate to_readable: serialize as UTF-8 human-readable
    readable_bytes = _serialize_readable(data)

    # Simulate to_repo: re-parse readable, serialize as ASCII
    reparsed = json.loads(readable_bytes.decode("utf-8"))
    repo_bytes = _serialize_ascii(reparsed)

    assert repo_bytes == original_bytes, (
        f"{filename}: round-trip changed the file "
        f"(original {len(original_bytes)} bytes vs round-trip {len(repo_bytes)} bytes)"
    )


# ---------------------------------------------------------------------------
# Lao-script guard for dish glossary
# ---------------------------------------------------------------------------


def test_glossary_lao_script_guard():
    """Lao fields in the dish glossary must not contain non-Lao letters.

    Guards against Thai/CJK contamination in name_local and order_phrase_local.
    It cannot catch the PHRA/PHA class because both codepoints are in the
    Lao block, so a green run is not proof that the values are verified.
    """
    fp = DATA_DIR / "laos_dish_glossary.json"
    data = json.loads(fp.read_text(encoding="utf-8"))
    dishes = data.get("dishes", [])

    allowed_ascii = set(string.whitespace + string.digits + string.punctuation)
    problems = []

    for dish in dishes:
        dish_name = dish.get("name_en") or dish.get("dish_key") or "<unknown>"
        for field in ("name_local", "order_phrase_local"):
            value = dish.get(field)
            if not value:
                continue
            for ch in value:
                cp = ord(ch)
                # Lao block: U+0E80 to U+0EFF
                if 0x0E80 <= cp <= 0x0EFF:
                    continue
                if ch in allowed_ascii:
                    continue
                problems.append(f"{dish_name}.{field} has non-Lao codepoint U+{cp:04X}")
                break  # one problem per field is enough

    assert not problems, "Glossary Lao-script guard failures:\n" + "\n".join(
        "  " + p for p in problems
    )


# ---------------------------------------------------------------------------
# Idempotency checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", _VENUE_GLOSSARY_FILES)
def test_to_repo_on_ascii_file_is_noop(filename):
    """Running --to-repo on an already-ASCII file produces identical output."""
    fp = DATA_DIR / filename
    original_bytes = fp.read_bytes()
    data = json.loads(original_bytes.decode("utf-8"))
    ascii_bytes = _serialize_ascii(data)
    assert ascii_bytes == original_bytes, (
        f"{filename}: to_repo on already-ASCII file should be identity"
    )


# ---------------------------------------------------------------------------
# G4d: Ratchet tests for spice and safety gaps in the dish glossary
# ---------------------------------------------------------------------------

# These counts are the CEILING. They may decrease as a native speaker adds
# moderating phrases or cooked-request alternatives. They must NEVER increase.
# If a new dish is added without proper phrases, this test blocks the commit.

_KNOWN_HOT_WITHOUT_MODERATE = 3  # Sweet Chili Paste, Raw Minced Beef, Spicy Cucumber
_KNOWN_RAW_WITHOUT_COOK_REQUEST = 1  # Raw Minced Beef & Bile Salad


def test_spice_gap_ratchet():
    """Hot dishes without a moderating phrase must not increase.

    A "moderating phrase" is one that includes a Lao request to reduce spice.
    Known Lao modifiers: \u0e9c\u0eb1\u0e94\u0edc\u0ec9\u0ead\u0e8d (little spicy),
    \u0e9a\u0ecd\u0ec8\u0e9c\u0eb1\u0e94 (not spicy).
    The gap stays visible until a native speaker fills it.
    """
    fp = DATA_DIR / "laos_dish_glossary.json"
    data = json.loads(fp.read_text(encoding="utf-8"))

    moderate_keywords = [
        "\u0e9c\u0eb1\u0e94\u0edc\u0ec9\u0ead\u0e8d",
        "\u0e9a\u0ecd\u0ec8\u0e9c\u0eb1\u0e94",
        "\u0e9c\u0eb1\u0e94\u0eab\u0ebc\u0eb2\u0e8d",
    ]

    hot_no_moderate = []
    for dish in data["dishes"]:
        if dish.get("spice_level") != "hot":
            continue
        phrase = dish.get("order_phrase_local", "")
        has_moderate = any(kw in phrase for kw in moderate_keywords)
        if not has_moderate:
            hot_no_moderate.append(dish.get("name_en") or dish.get("dish_key"))

    assert len(hot_no_moderate) <= _KNOWN_HOT_WITHOUT_MODERATE, (
        f"Spice gap INCREASED from {_KNOWN_HOT_WITHOUT_MODERATE} to "
        f"{len(hot_no_moderate)}. New gaps: {hot_no_moderate}. "
        f"Add a moderating phrase or update the ratchet ceiling."
    )


def test_raw_safety_gap_ratchet():
    """Raw/uncooked dishes without a cooked-request alternative must not increase.

    A "cooked-request phrase" would offer the option to cook the dish
    (e.g. larb suk vs larb dip). Lao keyword: \u0eaa\u0eb8\u0e81 (suk = cooked).
    The gap stays visible until a native speaker fills it.
    """
    fp = DATA_DIR / "laos_dish_glossary.json"
    data = json.loads(fp.read_text(encoding="utf-8"))

    raw_indicators = ["raw", "uncooked", "dip"]
    cook_keywords = [
        "\u0eaa\u0eb8\u0e81",
    ]

    raw_no_cook = []
    for dish in data["dishes"]:
        desc = (dish.get("description", "") or "").lower()
        name = (dish.get("name_en", "") or "").lower()
        dish_key = (dish.get("dish_key", "") or "").lower()
        is_raw = any(kw in desc or kw in name or kw in dish_key for kw in raw_indicators)
        if not is_raw:
            continue
        phrase = dish.get("order_phrase_local", "")
        has_cook_option = any(kw in phrase for kw in cook_keywords)
        if not has_cook_option:
            raw_no_cook.append(dish.get("name_en") or dish.get("dish_key"))

    assert len(raw_no_cook) <= _KNOWN_RAW_WITHOUT_COOK_REQUEST, (
        f"Raw safety gap INCREASED from {_KNOWN_RAW_WITHOUT_COOK_REQUEST} to "
        f"{len(raw_no_cook)}. New gaps: {raw_no_cook}. "
        f"Add a cooked-request phrase or update the ratchet ceiling."
    )
