# Genie brief: SPEC-43 Gap 3 -- do not fall back to an unapproved provider

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43. Do not enable personal-trip LLM. Do not start Armor,
Play Integrity, SQL cache wiring, `derived_feature`, hosted
0026, Flutter, deploy, or an APK. Do not scrub the
`_api_embedding` failure print this slice.

## Goal

`LLMService.complete` walks `HEAVY_FALLBACK`:
`gpt-4o`, then `claude-3-5-sonnet-20241022`, then
`gemini/gemini-1.5-pro`. A provider error is swallowed and the
same messages (already-redacted itinerary DTO plus question)
are sent to the next vendor. Gap 3 acceptance: provider
failure cannot route data to an unapproved provider.

This is SPEC-43 Gap 3 approved-model pin only. It is not a
GCP/legal matrix, not embeddings, not turning LLM on.

Read before editing:

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/llm_service.py` (`HEAVY_FALLBACK`, `LIGHT_FALLBACK`,
  `complete`)
- `config/settings.py` (`heavy_model`, `light_model`)
- `tests/test_spec43_g11_spend.py`
  (`test_fallback_chain_does_not_retry_next_model_on_spend_cap`,
  `test_provider_error_still_falls_back`)
- `tests/test_spec43_g3_itinerary_dto.py` (must stay green)
- `tests/test_spec43_g3_outbound_redact.py` (must stay green)
- `tests/test_spec43_g3_cache_embed.py` (must stay green)

Base branch: latest `main` (`4404ca9`), including Gap 3
cache-embed `b59c50d` (PR #162).

Create and push: `feat/spec43-g3-fallback`

Do not merge. Open one PR after the gates are green.

## Why this exists

Redaction does not stop a second vendor from receiving the
prompt. The hardcoded Claude/Gemini heavy chain is the remaining
cross-provider hop. Pin completions to the configured model for
that tier.

Do not invent a settings spreadsheet of regions and
subprocessors. Approved == `settings.heavy_model` on heavy,
`settings.light_model` on light.

## Current production seams to reuse

- Keep spend circuit. `SpendCapped` must still re-raise and
  never continue the loop
  (`test_fallback_chain_does_not_retry_next_model_on_spend_cap`
  stays green; if it unpacks three `HEAVY_FALLBACK` names,
  rewrite the unpack so it still proves SpendCapped is not
  swallowed. Do not weaken it).
- Keep DTO allowlist and outbound/cache redaction.
- Keep `except SpendCapped: raise`. Other provider errors must
  not hop to another vendor.
- `LIGHT_FALLBACK` is already one model (`gpt-4o-mini`). Pin it
  to `settings.light_model` the same way so an explicit
  unapproved `model=` cannot sneak a second vendor.
- Do not log messages, model names as secrets, or API keys.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.
Do not set `TB_LITELLM_API_KEY` in tests.

## Scope

### 1. Approved chain is the configured model

In `complete`:

- Heavy approved set is `{settings.heavy_model}` (the instance
  already copies this to `self.heavy_model`).
- Light approved set is `{settings.light_model}`.
- The attempt list is exactly that one model, first.
- If the caller passes `model=` that is not in the approved set
  for that `routing_tier`, do not call LiteLLM. Raise a
  `ValueError` (or similar typed error, not a bare `Exception`
  that the fallback `except Exception: continue` would swallow
  if someone reintroduces a loop).
- On a provider error from the approved model, do not try
  Claude, Gemini, or any other name. Surface the failure (keep
  today's final `RuntimeError` if the approved attempt failed,
  or re-raise the provider error -- pick one and test it).

You may delete or shrink class attributes `HEAVY_FALLBACK` /
`LIGHT_FALLBACK`. If they remain, they must not contain a
second vendor, and `complete` must not walk them as a
cross-provider chain.

Do not change `MODEL_COSTS` except as needed for compile.
Do not change embeddings this slice.

### 2. Named tests

Add `tests/test_spec43_g3_fallback.py`. No widgets. No live
Postgres. No real LiteLLM network.

Exact name:

`test_heavy_complete_does_not_fallback_to_unapproved_provider`

Monkeypatch `litellm.acompletion` so the first call raises
`RuntimeError("provider down")` and any later call would
succeed. Call `LLMService.complete` with `routing_tier="heavy"`
and a tiny messages list (no canaries required). Must not
return a successful completion from a second model. Captured
`model` kwargs must not include
`claude-3-5-sonnet-20241022` or `gemini/gemini-1.5-pro`.
LiteLLM is called at most once.

Also (any name):

- explicit `model="claude-3-5-sonnet-20241022"` with
  `routing_tier="heavy"` does not call LiteLLM
- `test_provider_error_still_falls_back` in
  `tests/test_spec43_g11_spend.py` currently asserts a hop to
  the second `HEAVY_FALLBACK` name. Update it so a provider
  error on the approved model does not call a second vendor.
  Do not weaken SpendCapped behaviour.
- DTO, outbound-redact, and cache-embed named tests stay green

Do not assert on comments.

### 3. R17 sabotage

Exact edit: restore walking the old three-name
`HEAVY_FALLBACK` on provider `Exception` (skip SpendCapped).

`test_heavy_complete_does_not_fallback_to_unapproved_provider`
must fail (a second vendor is called, or a successful
completion comes from Claude/Gemini). Restore before the PR.
Do not sabotage spend, DTO, or redaction.

If Databricks blocks in-place sabotage, an in-memory pytest
plugin that restores the three-vendor loop inside `complete`
only is the accepted substitute. Named test must still fail.
Drop the plugin before the PR.

## Out of scope

- Enabling LLM for personal trips
- Embedding failure `print`
- Regional/subprocessor contract matrix
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

SHA, branch, pytest last line, files touched. Named test in
the report must include
`test_heavy_complete_does_not_fallback_to_unapproved_provider`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
