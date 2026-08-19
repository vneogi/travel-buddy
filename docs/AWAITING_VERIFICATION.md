# Awaiting Verification

Consolidated Aug 14 2026. This file is a dated log of what cannot be verified
from a keyboard, plus the findings that were retracted and the tooling
incidents worth not repeating. It is the only place in the repo where dated
observations belong (R16).

What it deliberately does not carry: the device-day task order, which lives in
`docs/PROJECT_STATUS.md` with the runnable Windows PowerShell steps in
`docs/briefs/DEVICE_DAY.md`. Two documents holding the same ordered list is how
they end up contradicting each other, which is what this consolidation is
fixing.

Commits are identified by SHA only. Earlier revisions numbered work as `#84`,
`#85` and so on; those numbers cannot be reconciled against `git log`.

## What cannot be verified without a device or credentials

| Area | Unverified since | Verify with |
|---|---|---|
| Migrations 0011 to 0018 | applied device day 2026-08-17 | VALIDATE on NOT VALID CHECKs still deferred; confirm via Step 7 |
| The five Supabase tests | ran green 2026-08-17 | `280 passed` suite with TB_SUPABASE_URL; see finding below |
| Flutter client | Aug 9 | `flutter analyze && flutter test` on a device (now includes SPEC-22 render tests) |
| Migration 0019 prompt_dismissed | landed `1b9b1b3`, unapplied | Apply via Supabase SQL editor; then confirm signal_types drift still green |
| PowerShell scripts | Aug 9 | `.\scripts\smoke-test.ps1` on Windows |
| `hybrid_venue_search` geo_region parameter | Observed Aug 17 2026 | Live signature matches 0001: no geo_region arg (radius-only). Multi-city RPC filter still absent |
| Dubai row contents, including AED magnitudes | Cleared Aug 17 2026 | 16 Dubai venues live (null price_band). dubai_dishes=0 -- nothing to inspect for AED; food data is greenfield |
| `pg_description` non-ASCII | Cleared Aug 17 2026 | Step 7c returned 0 rows |

The five Supabase integration tests ran green on device day 2026-08-17 with
`TB_SUPABASE_URL` set (`280 passed` suite). Remaining credential-gated gaps
are Flutter, smoke-test.ps1, and deliberate VALIDATE of NOT VALID CHECKs.

## Open issues that need a person, not a test

### High -- the Dubai venues have no loader-valid source file

Durability landed as `data/dubai_uae_raw_snapshot.json` (`6bfa1c6`,
`not_loader_source: true`, 16 venues). Live `venue_dish` count for Dubai is
**0**. Still owed: curated `data/dubai_uae.json` that passes
`load_venues.py --dry-run` (fill null 0011 fields; map Dubai categories /
audiences / vibes into loader vocabulary; optionally add dishes). Do not pass
the raw dump to the loader.

### Medium -- two Lao vowel errors that no guard can catch

Script-range tests catch Chinese or Thai characters sitting in a Lao field.
They cannot catch a wrong vowel inside otherwise correct Lao. Two are known:
one in a Wat Mai name, and a suspected one in the `tam_mak_hoong` order phrase,
which reads as "do not fry much" where "not too spicy" is intended -- a missing
leading vowel. Both need a native reader. This is the reason the driver card
asks the traveller to confirm rather than asserting.

### Medium -- spice and raw-meat phrasing is incomplete

Four dishes are marked hot and only one carries a spice modifier phrase.
`laap_dib` is raw meat with no "cooked please" phrase at all. Related: the
raw-safety guard keys off the English word "raw" appearing in description
prose, so a reword silently disables it, and the spice keywords are spelled
with PHAT where PHET is meant. The keyword spelling must be corrected together
with the data, never separately, or the search stops matching today's text.


## Finding -- Aug 17 2026 -- Device Day closed

Full Windows device day completed. Durable outcomes:

- Dubai durability: `data/dubai_uae_raw_snapshot.json` at `6bfa1c6`
  (`not_loader_source`, 16 venues). Loader-valid `dubai_uae.json` still owed.
- 0011 dual-column gate: OpenAPI 22 columns; neither `name_local` nor
  `names_local`; applied 0011-0018 via Supabase SQL editor.
- Laos reload: 58 venues + 30 glossary; hours 58/58 structured.
- Pytest: `280 passed` with live `TB_SUPABASE_URL` (five Supabase tests included).
- price_band: dish vocab clean; venues_rag non-null matches 0017; 16 nulls =
  Dubai. VALIDATE deferred.
- Dubai `venue_dish` count live: **0** (confirms raw dump; no AED magnitudes
  to inspect). Food curation for Dubai is greenfield.
- pg_description non-ASCII: 0 rows.
- `hybrid_venue_search` live args = migration 0001 (no geo_region).

October spine next: itinerary signal/auth/CI fixes
(docs/briefs/GENIE_ITINERARY_SIGNAL_FIXES.md) -> SPEC-12 -> SPEC-10 -> thin
SPEC-04. SPEC-09 client and SPEC-22 October slice are merged; device E2E,
flutter test, and apply 0019 remain laptop follow-ups. After the fix PR
merges, planning-agent handoff is docs/HANDOFF_PLANNING_AGENT.md.

## Finding -- Aug 17 2026 -- Steps 5d + 7 live SQL (partial)

**5d opening hours:** all Laos venues have `opening_hours_structured` --
luang_prabang 23/23, vang_vieng 15/15, vientiane 20/20.

**7a price_band:**
- `venue_dish`: budget 28, mid 13, splurge 3 (no nulls; no `free`/`premium`).
- `venues_rag`: budget 35, free 5, mid 15, splurge 3, **null 16**.
  Non-null set matches 0017 CHECK (`budget`/`free`/`mid`/`splurge`). The 16
  nulls are the Dubai rows (known from raw dump). Do not VALIDATE today unless
  deliberately accepting NULL-as-allowed; CHECK already permits NULL.

**7b Dubai dishes:** `dubai_dishes = 0`. No AED magnitudes to observe. Raw
dump's `venue_dishes: 0` confirmed live.

Corrected 7b (already run):

```sql
SELECT count(*) AS dubai_dishes
FROM venue_dish vd
JOIN venues_rag v ON v.venue_id = vd.venue_id
WHERE v.geo_region LIKE '%dubai%';
-- Result: 0
```

**7c pg_description non-ASCII:** 0 rows. Live comments are ASCII.

**7d hybrid_venue_search:** live args match migration `0001` exactly (no
`geo_region` parameter -- radius-only).

## Finding -- Aug 17 2026 -- live pytest green: 280 passed

Second Step 6 run after LF-normalizing working-tree `laos*.json`:
`280 passed, 13 warnings in 58.42s`. Warnings include the five
`tests/test_supabase_integration.py` cases (DeprecationWarning from the
Supabase client) -- they ran with live creds and passed. Closes the
long-standing "five Supabase tests have never run" gap for this day.
Windows note: `git checkout -- data/*.json` alone did not clear CRLF;
explicit Python `\r\n` -> `\n` rewrite did.

## Finding -- Aug 17 2026 -- first live pytest: 270 passed, 10 failed

Step 5 real load succeeded (58 Laos venues, 30 glossary). Step 6 with
`TB_SUPABASE_URL` set: 270 passed, 10 failed, 13 warnings. The five tests in
`tests/test_supabase_integration.py` appear in the warnings list and are
absent from FAILED -- treated as ran-and-passed (R8: not skipped for missing
URL).

Failures classified:

- 8x `test_data_format` byte-identity: working-tree CRLF vs LF serializers
  (Windows `core.autocrlf`). Mitigation: `.gitattributes` `data/*.json
  text eol=lf` + renormalize on the laptop.
- `test_no_unexpected_non_ascii`: R14 arrows in DEVICE_DAY /
  ENGINEERING_RULES (fixed to `->` / `=>`).
- `test_no_silent_key_drop`: `dubai_uae_raw_snapshot.json` live-row keys
  (`created_at`, `source_url`, `trap_score`, `updated_at`). Guard now skips
  files with `not_loader_source: true`.

## Finding -- Aug 17 2026 -- Step 5 real load blocked on env name mismatch

Laos dry-runs passed (58 venues / 44 dishes; 2 expected market warnings).
Real `load_venues.py` failed at embedding: LiteLLM/OpenAI SDK required
`OPENAI_API_KEY` while `.env` carries `TB_LITELLM_API_KEY`. Real
`load_dish_glossary.py` failed looking for `TB_SUPABASE_SERVICE_KEY` while
canonical `.env.example` name is `TB_SUPABASE_KEY`. Fixed in loaders (map /
accept aliases) and DEVICE_DAY Step 5a preflight. Re-run after pull; no DB
writes from the failed venue attempt (crashed before upsert).

## Finding -- Aug 17 2026 -- empty venues_rag column dump must not unlock 0011

On device day Step 3b, `psql ... -U postgres` prompted for a password and the
piped TSV was empty (or auth noise). `device_day_name_column_decision.py`
printed `venues_rag columns: []` then `DECISION: safe to apply 0011`. That was
a false safe: the else-branch treated "neither name_local nor names_local"
as permission to apply when the real input was "no columns at all."

Action: do not apply 0011 on that output. Prefer OpenAPI Step 3a
(`device_day_schema_from_openapi.py`). Decision script now exits 2 on empty
input, password/FATAL transcripts, or missing core columns
(`venue_id` / `name` / `geo_region`). Do not pass `-U postgres` when
`TB_DATABASE_URL` already includes the role.

## Finding -- Aug 16 2026 -- Dubai loader export refused; raw dump committed

Device-day Step 2 tried `export_dubai_from_snapshot.py` then
`load_venues.py --dry-run` on `data/dubai_uae.json`. Dry-run exited non-zero
with 72 errors. Cause, verified from the committed raw dump:

- All 16 Dubai rows have null `typical_dwell_minutes`, `indoor_outdoor`, and
  `price_band` (columns present, values null).
- Categories outside the Laos-era loader set include `gallery`, `beach_club`,
  `shopping`, `attraction`, `community_space`.
- Audiences outside the set include `creative_professional`, `art_enthusiast`,
  `collector`, `food_enthusiast`.
- Vibe tag `executive` is not in `VALID_VIBE_TAGS` (though `executive` exists
  as an audience).

Decision: do not invent field values mid device-day. Commit
`data/dubai_uae_raw_snapshot.json` (`not_loader_source: true`, 6bfa1c6) for
durability, continue migrations from Step 3, and treat loader-valid
`data/dubai_uae.json` as a follow-up curation plus vocabulary decision.
The raw dump recorded `venue_dishes: 0`; confirm against the local
`live_snapshot/*/venue_dish.json` whether any Dubai dishes exist before
relying on that number.

## Finding -- Aug 14 2026 -- SPEC-04 October scope shrunk

`docs/CONSUMER_SURFACE_ROADMAP.md` said the October trip needed SPEC-09, the
driver card, and the offline vault. `docs/PROJECT_STATUS.md` omitted SPEC-04
from the numbered next list and left booking anchors at item 8. Both were
wrong relative to the forcing function ("full context" on real bookings).

Checked against what is already shipped: SPEC-02 already delivers outbox,
SyncEngine, `cache_trip` and `cache_place`. SPEC-12 already specifies the
venue driver card offline from `cache_place`. The unique SPEC-04 remainder
that matters for October is a thin rescue entry to the hotel address card
once SPEC-10 exists. `cache_vault`, pass tiles, emergency grid and phrase
packs are post-field-test. SPEC-04, PROJECT_STATUS and CONSUMER_SURFACE were
amended the same day; device-day steps live in `docs/briefs/DEVICE_DAY.md`.

## Closed since the last revision

Recorded because each was open long enough to be quoted elsewhere, and a reader
finding a stale copy of this file should be able to tell.

- **VALID_DISH_CONTAINS lived in the glossary loader.** Fixed in PR #15
  (`d061222`). Constant now lives in `config/dietary.py`; loader imports it;
  identity and set-equality guards land in `tests/test_valid_dish_contains.py`.
  The same PR also ruff-formatted the device-day helper scripts that had made
  main's format check red since `d062b5a`.
- **The loader discarded five curated fields per venue.** Fixed. The loader
  writes them and a schema-drift guard compares its write set against the
  migrations.
- **Wrong script in Lao fields.** Fixed. All three token classes are clean, and
  ten verified names carry a source and a reference.
- **Halal plus pork passed the allergen check.** Closed by retirement rather
  than by a rule. SPEC-14 retired the dietary suitability claim entirely, on
  the grounds that no source could support it. Ingredient facts remain,
  informational and disclaimed.
- **`mobility_limited` overcorrected.** The "roughly two thirds" figure was
  wrong; it is 17 of 58. The 40 of 58 figure belongs to `seniors` and the two
  were conflated.
- **The loader emitted 58 false warnings per run** about missing structured
  opening hours while its own fallback read the unstructured key. Fixed; the
  warning now fires only when both are absent, which made the two real warnings
  visible.
- **Signal provenance was computed and discarded.** `clock_skew_seconds` had
  never been persisted for any signal, leaving SPEC-02 Part C unmet in the live
  write path. Both backends now accept and store it, guarded by a test that
  drives the ingest endpoint.
- **The lint job had never passed.** See the tooling section below.

## Retracted findings

Kept because the cost of each was real and the pattern repeats.

### The pytest filterwarnings entry was not broken

A previous revision recorded as a Medium issue that `pyproject.toml` referenced
a warning class that does not exist. It does exist. The startup error came from
invoking the base compute's system pytest before installing requirements -- an
environment mistake reported as a repo defect.

What survives is smaller: naming a class in an ini `filterwarnings` entry is a
hard dependency on that class existing, and the entry only ever suppressed a
warning rather than enforcing anything. Cost: one unnecessary config change and
one over-strict version pin, both because a brief asserted something that was
not there and the executing agent matched the brief instead of contradicting
it.

### SPEC-12 was never blocked on curation

The spec claimed no Laos venue carried Lao script and that curating 58 of them
was the critical path. Both were wrong; all 58 already carried the fields. The
blocker was the loader discarding them. Cost: an instruction to the project
owner to spend days on data entry that was already done.

## Tooling incidents

### The lint job had never passed -- RESOLVED Aug 14

`ci.yml` chains lint, test, build and deploy, each needing the one before. The
lint job failed on every run as far back as the retained history, so build and
deploy never executed once in the life of the repository. The only meaningful
check was a separate `test.yml` workflow running pytest, which is why a dead
pipeline stayed invisible: pull requests showed a green test beside a red lint,
and lint was not a required check.

Causes were mundane -- a Dockerfile named with a `.py` extension that ruff
parsed as Python, deliberate late imports in tests, and a handful of real
errors. One of those real errors was a live `NameError`: `logger.info` was
called in the signal router with nothing defining `logger`.

Two lessons worth keeping. An unpinned linter install means the gate depends on
whichever version released most recently, so the pin is part of the fix. And a
formatter that wants a whole-tree reformat is not a reason to drop the gate:
the reformat goes in one isolated commit whose SHA is recorded in
`.git-blame-ignore-revs`, which both GitHub and `git blame --ignore-revs-file`
honour.

### Cloud agents are unavailable

The Databricks team enforces Privacy Mode (Legacy), which blocks cloud
subagents outright. Work needing a real Python environment therefore goes to
the execution agent; the planning side has no pytest and no ruff.

### runGit outage, Aug 11-12 -- RESOLVED

A session found `runGit` failing with `Git folder (Repo) has invalid type`
after a previous session died mid-task. Repair was a re-clone, not a retry.
The CLI allow-list refuses `repos delete`, so recovery went through the Repos
API, and re-cloning over the existing path fails until the old folder is
removed.

### Bytecode writes are denied on the compute

The same filter that blocks workspace writes also blocks bytecode caching, so
pytest fails on import there until it is run with `PYTHONDONTWRITEBYTECODE=1`.

### Half-landed documentation commit

A commit rebuilt `PROJECT_STATUS.md` only partially and left a new summary
prepended to the stale original, so the file asserted two contradictory things
about signal types. The failure was silent. This is the reason documentation
edits are verified by reading back the committed file rather than trusting the
write.
