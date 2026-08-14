"""Documentation hygiene guard.
Three failure modes have each cost real time here, and all three are
statically detectable:
- Non-ASCII bytes have silently blocked edits in the workspace layer, so an
  edit reported success and did not land (R14). The trigger turned out to be
  narrower than first assumed and git plumbing bypasses it entirely, but ASCII
  documents remain cheap insurance and keep diffs reviewable, so the guard
  stays.
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
NON_ASCII_ALLOWLIST = frozenset(
    {
        "docs/DATA_MODEL_BRD.md",
        "docs/UX_BACKLOG.md",
        "docs/VISION.md",
        "docs/research/survey_deep.md",
        "docs/research/survey_short.md",
        "docs/specs/SPEC-01-migrations-and-first-signal.md",
        "docs/specs/SPEC-02-offline-queue-and-sync.md",
        "docs/specs/SPEC-03-party-context.md",
        "docs/specs/SPEC-04-offline-vault.md",
        "docs/specs/SPEC-05-observability.md",
        "docs/specs/SPEC-06-behavioral-signals.md",
        "docs/specs/SPEC-07-signal-emission.md",
        "docs/specs/SPEC-09-anonymous-identity.md",
        "mobile/README.md",
        "scripts/README.md",
        "supabase/migrations/README.md",
    }
)

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

EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".dart_tool",
        "node_modules",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "Pods",
        ".gradle",
    }
)


def _rel(path):
    return path.relative_to(REPO_ROOT).as_posix()


def _tracked_docs():
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.md")
        if p.is_file() and not EXCLUDED_PARTS & set(p.relative_to(REPO_ROOT).parts)
    )


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
            context = raw[max(0, at - 30) : at + 30].decode("utf-8", "replace")
            offenders[rel] = (len(bad), context)
    assert not offenders, (
        "Non-ASCII silently blocks editAsset (R14). Use -- for an em-dash "
        "and -> for an arrow.\n"
        + "\n".join(
            "  %s: %d byte(s), near: %r" % (k, v[0], v[1]) for k, v in sorted(offenders.items())
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
        "not LangGraph and db_provider needs no manual flip.\n" + "\n".join(offenders)
    )


def _tracked_code_files():
    """Return .py and .sql files under the same EXCLUDED_PARTS filter."""
    results = []
    for ext in ("*.py", "*.sql"):
        results.extend(
            p
            for p in REPO_ROOT.rglob(ext)
            if p.is_file() and not EXCLUDED_PARTS & set(p.relative_to(REPO_ROOT).parts)
        )
    return sorted(results)


def test_every_spec_reference_resolves():
    spec_dir = REPO_ROOT / "docs" / "specs"
    missing = {}
    # Scan markdown docs AND code/sql files
    for path in list(_tracked_docs()) + _tracked_code_files():
        text = path.read_text(encoding="utf-8")
        for num in sorted(set(SPEC_REF_RE.findall(text))):
            if not list(spec_dir.glob("SPEC-%s-*.md" % num)):
                missing.setdefault("SPEC-" + num, []).append(_rel(path))
    assert not missing, (
        "A SPEC reference resolving to nothing hides an uncommitted spec.\n"
        + "\n".join("  %s referenced by %s" % (k, ", ".join(v)) for k, v in sorted(missing.items()))
    )


# ---------------------------------------------------------------------------
# Non-ASCII guards for code (.py and .sql)
# ---------------------------------------------------------------------------

import ast
import io
import tokenize as _tokenize


def _extract_comment_on_bodies(sql: str):
    """Yield (line_number, body_text) for each COMMENT ON ... IS '...' in sql.

    Matches both single-line and multi-line COMMENT ON statements. Returns the
    text between the IS quotes, which is what Postgres persists to pg_description.
    """
    # Match: COMMENT ON ... IS '<body>';  (body may span lines)
    pattern = re.compile(
        r"COMMENT\s+ON\s+\w+.*?IS\s*\n?\s*'((?:[^']|'')*)'",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(sql):
        # Line number of the IS keyword (where the body starts)
        line_num = sql[: match.start(1)].count("\n") + 1
        yield line_num, match.group(1)


def _python_comment_and_docstring_chars(filepath: Path):
    """Yield (line, col, char, codepoint) for non-ASCII in comments and docstrings.

    Uses tokenize for COMMENT tokens and ast for docstrings. String literals
    that are not docstrings are intentionally exempt -- the program may
    legitimately emit degree signs, section references, or other symbols.

    .dart files are excluded from this guard entirely. Display strings in a
    client that renders Lao and Arabic are legitimately non-ASCII; localisation
    belongs in ARB files, not under a byte-level ASCII guard.
    """
    source = filepath.read_text(encoding="utf-8")
    hits = []

    # 1. COMMENT tokens (lines starting with #)
    try:
        tokens = list(_tokenize.generate_tokens(io.StringIO(source).readline))
    except _tokenize.TokenError:
        return hits  # Unparseable file -- skip gracefully
    for tok in tokens:
        if tok.type == _tokenize.COMMENT:
            for i, ch in enumerate(tok.string):
                if ord(ch) > 127:
                    hits.append((tok.start[0], tok.start[1] + i, ch, ord(ch)))

    # 2. Docstrings via AST
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return hits  # Unparseable -- skip gracefully

    docstring_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ds_node = node.body[0].value
                for ln in range(ds_node.lineno, ds_node.end_lineno + 1):
                    docstring_lines.add(ln)

    source_lines = source.splitlines()
    for ln in sorted(docstring_lines):
        if ln <= len(source_lines):
            line_text = source_lines[ln - 1]
            for col, ch in enumerate(line_text):
                if ord(ch) > 127:
                    hits.append((ln, col, ch, ord(ch)))

    return hits


def _count_comment_on_occurrences(sql: str) -> list:
    """Return line numbers where COMMENT ON appears (case-insensitive).

    Used to verify that _extract_comment_on_bodies parsed every statement.
    """
    lines = []
    for i, line in enumerate(sql.splitlines(), 1):
        # Match COMMENT ON at start of a non-comment line
        stripped = line.strip()
        if stripped.upper().startswith("COMMENT ON") and not stripped.startswith("--"):
            lines.append(i)
    return lines


def test_no_non_ascii_in_sql_comment_on():
    """No non-ASCII character may appear inside a COMMENT ON body in .sql files.

    Justification: COMMENT ON text persists into pg_description in the live
    database. A non-ASCII character (especially an em-dash U+2014 or curly
    quote) will be stored verbatim. If the client or connection is not UTF-8
    the value becomes mojibake that cannot be distinguished from corruption.
    This has occurred once (0015 draft, already fixed).

    Applied migrations (0001-0014) are included because this is a read-only
    assertion -- if they already pass, nothing changes; if a future edit adds
    a COMMENT ON, the guard catches it.
    """
    offenders = []
    for path in sorted(REPO_ROOT.rglob("*.sql")):
        if not path.is_file():
            continue
        rel = _rel(path)
        if EXCLUDED_PARTS & set(path.relative_to(REPO_ROOT).parts):
            continue
        sql = path.read_text(encoding="utf-8")
        for line_num, body in _extract_comment_on_bodies(sql):
            for col, ch in enumerate(body):
                if ord(ch) > 127:
                    offenders.append(
                        f"  {rel}:{line_num} col {col}: '{ch}' (U+{ord(ch):04X}) in COMMENT ON body"
                    )
    assert not offenders, (
        "Non-ASCII inside COMMENT ON persists to pg_description. "
        "Use ASCII equivalents (-- for em-dash, etc).\n" + "\n".join(offenders)
    )


def test_sql_comment_on_extraction_is_complete():
    """Every COMMENT ON statement must be parsed by _extract_comment_on_bodies.

    A COMMENT ON using dollar-quoting ($$body$$) or E-string (E\'body\')
    would silently bypass the single-quote regex. This test fails loudly
    naming the unparsed statement, converting a silent miss into a loud one
    without needing a full SQL parser.
    """
    unparsed = []
    for path in sorted(REPO_ROOT.rglob("*.sql")):
        if not path.is_file():
            continue
        rel = _rel(path)
        if EXCLUDED_PARTS & set(path.relative_to(REPO_ROOT).parts):
            continue
        sql = path.read_text(encoding="utf-8")
        occurrence_lines = _count_comment_on_occurrences(sql)
        extracted_count = sum(1 for _ in _extract_comment_on_bodies(sql))
        if extracted_count != len(occurrence_lines):
            # Identify which ones were missed
            extracted_lines = set()
            for match in re.finditer(
                r"COMMENT\s+ON\s+\w+.*?IS\s*\n?\s*\'((?:[^\']|\'\')*)\'",
                sql,
                re.IGNORECASE | re.DOTALL,
            ):
                extracted_lines.add(sql[: match.start()].count("\n") + 1)
            for line_num in occurrence_lines:
                if line_num not in extracted_lines:
                    line_text = sql.splitlines()[line_num - 1].strip()[:80]
                    unparsed.append(f"  {rel}:{line_num}: {line_text}")
    assert not unparsed, (
        "COMMENT ON statement(s) not parsed by the extraction regex. "
        "Likely uses dollar-quoting ($$) or E-string (E'...') instead "
        "of single quotes. Extend _extract_comment_on_bodies to handle it.\n" + "\n".join(unparsed)
    )


def test_no_non_ascii_in_python_comments_or_docstrings():
    """No non-ASCII character may appear in Python comments or docstrings.

    Justification (narrower than a blanket file scan, and each reason is real):

    1. In .sql COMMENT ON bodies, non-ASCII persists into the database (tested
       separately above).

    2. In .py comments and docstrings, keeping prose ASCII ensures that a
       mojibake round-trip through a non-UTF-8 tool shows up as a diff rather
       than silent corruption. It also keeps every non-ASCII string an explicit
       \\uXXXX escape, making the encoding choice visible and reviewable.

    String literals are intentionally EXEMPT. A degree sign in a temperature
    format string is correct code; forcing \\u00b0 makes it worse. This
    product renders Lao and Arabic -- a blanket ban on non-ASCII literals
    would fight the code rather than protect it.

    .dart files are deliberately excluded. Display strings in a Flutter client
    are legitimately non-ASCII; localisation belongs in ARB files, not under
    this guard.

    When a test genuinely needs a native-script string (e.g. proving the Lao
    script guard works), the prescribed form is \\uXXXX escapes in a string
    literal, which is pure ASCII. The answer is never an allowlist entry.
    """
    offenders = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if not path.is_file():
            continue
        rel = _rel(path)
        if EXCLUDED_PARTS & set(path.relative_to(REPO_ROOT).parts):
            continue
        for line_num, col, ch, codepoint in _python_comment_and_docstring_chars(path):
            offenders.append(f"  {rel}:{line_num} col {col}: '{ch}' (U+{codepoint:04X})")
    assert not offenders, (
        "Non-ASCII in comments/docstrings. Use ASCII equivalents "
        "(-- for em-dash, -> for arrow) or \\uXXXX in string literals.\n" + "\n".join(offenders)
    )
