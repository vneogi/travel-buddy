"""SPEC-43 Gap 10: redact secrets before diagnostics are retained.

Applied on write to the in-memory error ring and to the unhandled-exception
log line. Replacement text is the literal ``REDACTED``. The original value is
never logged.
"""

from __future__ import annotations

import re

REDACTED = "REDACTED"

# SPEC-43 Gap 8 / Gap 3: restricted needles (booking codes, notes) shorter
# than this would match ordinary prose, so they are ignored.
MIN_RESTRICTED_NEEDLE_LEN = 6

# Settings fields whose literal values must never appear in diagnostics.
SECRET_SETTING_FIELDS = (
    "litellm_api_key",
    "gemini_api_key",
    "google_maps_api_key",
    "google_places_api_key",
    "openweather_api_key",
    "supabase_key",
    "supabase_jwt_secret",
    "stripe_secret_key",
    "stripe_webhook_secret",
)

# Too-short literals would shred ordinary text; real keys are long.
_MIN_LITERAL_LEN = 6

_QUERY_SECRET = re.compile(
    r"(?i)(?<![A-Za-z0-9])(api_key|apikey|key|access_token|token|secret|password)=([^&\s'\"<>]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_OPENAI_STYLE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}")
_GOOGLE_STYLE = re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{10,}")


def _settings_literals() -> list[str]:
    try:
        from config.settings import settings
    except Exception:  # noqa: BLE001 -- redaction must never raise
        return []
    values = []
    for field in SECRET_SETTING_FIELDS:
        value = getattr(settings, field, None)
        if isinstance(value, str) and len(value) >= _MIN_LITERAL_LEN:
            values.append(value)
    # Longest first so a key that contains another key is fully replaced.
    return sorted(set(values), key=len, reverse=True)


def redact_secrets(text: str) -> str:
    """Return *text* with keys, tokens and configured secrets replaced."""
    if not text:
        return text or ""
    out = str(text)
    for literal in _settings_literals():
        out = out.replace(literal, REDACTED)
    out = _QUERY_SECRET.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    out = _BEARER.sub(f"Bearer {REDACTED}", out)
    out = _OPENAI_STYLE.sub(REDACTED, out)
    out = _GOOGLE_STYLE.sub(REDACTED, out)
    return out


def _usable_needles(extra_needles) -> list:
    values = set()
    for needle in extra_needles or ():
        if needle is None:
            continue
        value = str(needle).strip()
        if len(value) >= MIN_RESTRICTED_NEEDLE_LEN:
            values.add(value)
    # Longest first so a needle that contains another is replaced whole.
    return sorted(values, key=len, reverse=True)


def redact_outbound_llm_text(text: str, extra_needles=()) -> str:
    """SPEC-43 Gap 3: text about to leave the process for a model provider.

    redact_secrets first, then every occurrence of each extra needle
    (stripped, >= MIN_RESTRICTED_NEEDLE_LEN chars) becomes REDACTED.
    """
    if not text:
        return text or ""
    out = redact_secrets(text)
    for needle in _usable_needles(extra_needles):
        out = out.replace(needle, REDACTED)
    return out
