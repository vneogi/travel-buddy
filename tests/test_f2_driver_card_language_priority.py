"""F2: the Dart driver card language priority mirrors REGION_LANGUAGES.

Reads mobile/lib/features/driver_card/driver_card_helpers.dart as text (no
Flutter needed), parses the ordered rules inside languagePriority, and
resolves each region the way the Dart does: the first rule whose needle is
contained in the lower-cased region wins, otherwise the final fallback.
Adding a region to REGION_LANGUAGES without a matching client rule fails.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import load_venues as lv  # noqa: E402

DART = REPO_ROOT / "mobile" / "lib" / "features" / "driver_card" / "driver_card_helpers.dart"
_RULE = re.compile(r"^\s*if \(region\.contains\('([^']+)'\)\) return const \[([^\]]*)\];\s*$")
_FALLBACK = re.compile(r"^\s*return const \[([^\]]*)\];\s*$")


def _langs(raw):
    return [s.strip().strip("'") for s in raw.split(",") if s.strip()]


def _parse_rules():
    """Return ([(needle, [langs])...], fallback_langs) from languagePriority."""
    text = DART.read_text(encoding="utf-8")
    body = text.split("List<String> languagePriority(", 1)[1].split("\n}", 1)[0]
    rules, fallback = [], None
    for line in body.splitlines():
        m = _RULE.match(line)
        if m:
            rules.append((m.group(1), _langs(m.group(2))))
            continue
        m = _FALLBACK.match(line)
        if m:
            fallback = _langs(m.group(1))
    return rules, fallback


def _resolve(region):
    rules, fallback = _parse_rules()
    lowered = (region or "").lower()
    for needle, langs in rules:
        if needle in lowered:
            return langs
    return fallback


def test_parser_reads_the_expected_rules():
    rules, fallback = _parse_rules()
    assert [needle for needle, _ in rules] == ["laos", "dubai", "tanzania"]
    assert dict(rules) == {
        "laos": ["lo", "th", "en"],
        "dubai": ["ar", "en"],
        "tanzania": ["sw", "en"],
    }
    assert fallback == ["en"]


def test_client_first_language_matches_loader_for_every_region():
    assert lv.REGION_LANGUAGES
    mismatches = {
        region: (lang, _resolve(region)[0])
        for region, lang in lv.REGION_LANGUAGES.items()
        if _resolve(region)[0] != lang
    }
    assert mismatches == {}


def test_tanzania_regions_resolve_to_swahili_then_english():
    for region in ("zanzibar_tanzania", "nungwi_tanzania"):
        assert lv.REGION_LANGUAGES[region] == "sw"
        assert _resolve(region) == ["sw", "en"]


def test_unknown_region_falls_back_to_english():
    assert _resolve("paris_france") == ["en"]
    assert _resolve("") == ["en"]
    assert _resolve(None) == ["en"]


def test_driver_card_helpers_is_ascii():
    assert DART.read_text(encoding="utf-8").isascii()
