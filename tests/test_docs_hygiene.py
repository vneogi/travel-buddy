"""Documentation hygiene guard.
Three failure modes have each cost real time here, and all three are
statically detectable:
- Non-ASCII bytes silently block editAsset, so an edit reports success and
  does not land (R14).
- A document that mirrors a test count drifts, and a stale number is worse
  than no number (R16).
- A SPEC reference that resolves to nothing hides a spec that was never
  committed. SPEC-08 was executed in full and absent from the repo for weeks.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Accuracy here is load-bearing. Counts and architecture claims are checked
# only in these; specs are point-in-time records.
LIVING_DOCS = (
    "README.md",
    "MASTER_BRD.md",
    "docs/PROJECT_STATUS.md",
    "docs/TESTING_GUIDE.md",
)

# Measured Aug 12 2026. May only shrink.
NON_ASCII_ALLOWLIST = frozenset({
    "docs/VISION.md",
    "docs/DATA_MODEL_BRD.md",
    "docs/UX_BACKLOG.md",
    "docs/research/SURVEY_FINDINGS.md",
    "docs/research/survey_short.md",
    "docs/research/survey_deep.md",
    "docs/specs/SPEC-01-migrations-and-first-signal.md",
    "docs/specs/SPEC-02-offline-queue-and-sync.md",
    "docs/specs/SPEC-03-party-context.md",
    "docs/specs/SPEC-04-offline-vault.md",
    "docs/specs/SPEC-05-observability.md",
    "docs/specs/SPEC-06-behavioral-signals.md",
    "docs/specs/SPEC-07-signal-emission.md",
    "docs/specs/SPEC-09-anonymous-identity.md",
    "docs/specs/SPEC-10-booking-anchors.md",
})

FORBIDDEN_CLAIMS = (
    "LangGraph State Machine",
    "LangGraph orchestrator",
    "flip 3 imports",
    "3 import swaps",
    "still uses in-memory",
    "OFF until import swap",
)

COUNT_RE = re.compile(r"\b\d+\s+(?:passed|failed|skipped)\b")
SPEC_REF_RE = re.compile(r"SPEC-(\d{2})")


def _rel(path):
    return path.relative_to(REPO_ROOT).as_posix()


def _tracked_docs():
    docs = [REPO_ROOT / "README.md", REPO_ROOT / "MASTER_BRD.md"]
    docs += sorted((REPO_ROOT / "docs").rglob("*.md"))
    return [p for p in docs if p.is_file()]


def _living_docs():
    return [REPO_ROOT / n for n in LIVING_DOCS if (REPO_ROOT / n).is_file()]


def test_no_unexpected_non_ascii():
    offenders = {}
    for path in _tracked_docs():
        rel = _rel(path)
        if rel in NON_ASCII_ALLOWLIST:
            continue
        raw = path.read_bytes()
        bad = [i for i, b in enumerate(raw) if b > 127]
        if bad:
            at = bad[0]
            context = raw[max(0, at - 30):at + 30].decode("utf-8", "replace")
            offenders[rel] = (len(bad), context)
    assert not offenders, (
        "Non-ASCII silently blocks editAsset (R14). Use -- for an em-dash "
        "and -> for an arrow.\n"
        + "\n".join(
            "  %s: %d byte(s), near: %r" % (k, v[0], v[1])
            for k, v in sorted(offenders.items())
        )
    )


def test_non_ascii_allowlist_only_shrinks():
    stale = []
    for rel in sorted(NON_ASCII_ALLOWLIST):
        path = REPO_ROOT / rel
        if not path.is_file():
            stale.append("%s: allowlisted but no longer exists" % rel)
        elif not any(b > 127 for b in path.read_bytes()):
            stale.append("%s: now pure ASCII -- remove from the allowlist" % rel)
    assert not stale, "The allowlist must shrink:\n" + "\n".join(stale)


def test_living_docs_do_not_hardcode_test_counts():
    offenders = []
    for path in _living_docs():
        lines = path.read_text(encoding="utf-8").splitlines()
        for num, line in enumerate(lines, 1):
            if COUNT_RE.search(line):
                offenders.append("%s:%d: %s" % (_rel(path), num, line.strip()))
    assert not offenders, (
        "A mirrored count goes stale (R16). Tell the reader to run "
        "pytest -q -ra instead.\n" + "\n".join(offenders)
    )


def test_living_docs_make_no_false_architecture_claims():
    offenders = []
    for path in _living_docs():
        text = path.read_text(encoding="utf-8")
        for claim in FORBIDDEN_CLAIMS:
            if claim in text:
                offenders.append("%s: %r" % (_rel(path), claim))
    assert not offenders, (
        "These describe a system that does not exist. The orchestrator is "
        "not LangGraph and db_provider needs no manual flip.\n"
        + "\n".join(offenders)
    )


def test_every_spec_reference_resolves():
    spec_dir = REPO_ROOT / "docs" / "specs"
    missing = {}
    for path in _tracked_docs():
        text = path.read_text(encoding="utf-8")
        for num in sorted(set(SPEC_REF_RE.findall(text))):
            if not list(spec_dir.glob("SPEC-%s-*.md" % num)):
                missing.setdefault("SPEC-" + num, []).append(_rel(path))
    assert not missing, (
        "A SPEC reference resolving to nothing hides an uncommitted spec.\n"
        + "\n".join(
            "  %s referenced by %s" % (k, ", ".join(v))
            for k, v in sorted(missing.items())
        )
    )
