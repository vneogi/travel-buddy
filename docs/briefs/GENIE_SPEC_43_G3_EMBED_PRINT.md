# Genie brief: SPEC-43 Gap 3 -- embedding failure must not print provider text

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43. Do not enable personal-trip LLM. Do not start Armor,
Play Integrity, SQL cache wiring, `derived_feature`, hosted
0026, Flutter, deploy, or an APK.

## Goal

`services/embedding_service.py` `_api_embedding` has a safety net:

    except Exception as e:
        print(f"API embedding failed, falling back to synthetic: {e}")
        return self._synthetic_embedding(text)

Provider exceptions can echo the request input. `{e}` puts that
text on stdout (Cloud Run logs). The text may hold a booking
canary that the outbound redactor was meant to strip before the
call.

Acceptance: a provider failure on the embedding path writes no
provider exception text to stdout, stderr, or logs. The
synthetic fallback and its return value stay the same.

This is the Gap 3 embedding-print remainder only. It is not the
space-mixing policy, not a new provider, not the LLM path.

## Base

Latest `main` (`74a86ca`), including Gap 3 fallback pin
`8d8b28b` (PR #165).

Create and push: `feat/spec43-g3-embed-print`

Do not merge. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/embedding_service.py` (`_api_embedding`, `__init__`)
- `monitoring/redact.py` (`redact_outbound_llm_text`,
  `MIN_RESTRICTED_NEEDLE_LEN`)
- `tests/test_spec43_g3_cache_embed.py` (pattern for embedding
  canaries; must stay green)
- `tests/test_spec43_g11_spend.py` (SpendCapped on embed path
  must stay green)
- `main.py` for the existing logger name `travelbuddy`

No CREATE TABLE. No Flutter. No live Postgres. Do not set
`TB_LITELLM_API_KEY` in tests.

## Scope

### 1. Replace the print with a non-content log

In the `except Exception as e:` branch of `_api_embedding`:

- Remove the `print`.
- Use the stdlib logger `logging.getLogger("travelbuddy")`,
  level WARNING, with a fixed message. Example shape only:
  `logger.warning("embedding provider failed; using synthetic fallback (%s)", type(e).__name__)`
- Log the exception **class name only**. Do not include `str(e)`,
  `repr(e)`, `e.args`, the input text, the outbound text, or any
  needle.
- Keep `return self._synthetic_embedding(text)` unchanged.
- Keep `except SpendCapped: raise` above it unchanged.
- Keep the existing comment about mixing vectors; you may
  shorten it. Do not change the synthetic-vs-real policy.

Do not add a dependency. Do not change `generate_embedding`,
`batch_generate`, `_synthetic_embedding`, or the cache service.

### 2. Named test

New file `tests/test_spec43_g3_embed_print.py`. No live network.
Monkeypatch `litellm.embedding` to raise
`RuntimeError("EMBED-CANARY-g3-print echo of input")`.

Build the service with `EmbeddingService(use_synthetic=False,
circuit=SpendCircuit(max_process_usd=1e9, max_identity_usd=1e9))`.
If `configure_provider_keys()` needs a key, monkeypatch it to a
no-op in the test; do not set a real key.

Exact name:

`test_api_embedding_failure_does_not_leak_exception_text`

Use `capsys` and `caplog` (WARNING). Assert:

- call `generate_embedding("hello", user_id="u")` returns a list
  of length `settings.embedding_dimensions` (synthetic path);
- `"EMBED-CANARY-g3-print"` is not in `capsys.readouterr()`
  stdout or stderr;
- `"EMBED-CANARY-g3-print"` is not in any `caplog` record message
  or formatted text;
- `capsys` stdout is empty for this call (no print at all).

Also add (any name) one assertion that the WARNING record exists
and its text includes `RuntimeError` but not the canary.

Do not weaken SpendCapped tests or the cache-embed tests.

### 3. R17 sabotage

Exact edit: restore `print(f"API embedding failed, falling back to synthetic: {e}")`
in the except branch.

`test_api_embedding_failure_does_not_leak_exception_text` must
fail (the canary appears on stdout). Restore before the PR.
If Databricks blocks in-place sabotage, an in-memory pytest
plugin that patches only `_api_embedding` is the accepted
substitute. Drop the plugin before the PR.

## Out of scope

- Space-mixing or lexical-fallback policy (SPEC-44 embedding space)
- Cache or LLM prompt changes
- Personal-trip LLM enablement
- Armor, Play Integrity, Flutter, deploy, APK, 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.
Do not "fix" `test_today_tonight_includes_venue_name` or
`test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched. Named test in the
report must include
`test_api_embedding_failure_does_not_leak_exception_text`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
