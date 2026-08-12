# Awaiting Verification

No test laptop available until roughly Aug 17 2026. Nothing below can be
verified on device or against real Supabase until then.

pytest is the only real verification available in this window. Anything
touching Dart, PowerShell, or a live database is marked UNVERIFIED.

This file is a dated log. It is expected to go stale, and it is the only
place in the repo where dated observations belong (R16).

## A note on commit numbers

Earlier revisions of this file tracked work as `#84`, `#85`, `#86` and so
on. Those numbers cannot be reconciled against `git log` and had already
drifted, so they are dropped. Commits are identified by SHA only.

## Baseline, Aug 12 2026

A fresh clone on the Databricks compute at `0053cb7` reports 122 passed
and 5 skipped. All five skips are in `tests/test_supabase_integration.py`
with the reason "Supabase creds not configured (TB_SUPABASE_URL unset)".
Those are the expected skips. A skip anywhere else is a finding (R8).

## Verified via pytest

### arrival_delta server derivation -- 564fd7d

Derives `arrival_delta` from `visited_confirmed.captured_at` against
`node.scheduled_start`, so one tap yields two data points. Covered by
`services/arrival_delta_service.py` and `tests/test_arrival_delta.py`.
This is DONE. Earlier revisions of PROJECT_STATUS.md listed it as the
next task, contradicting this file.

### Documentation hygiene guard -- 8b71949, widened in 0053cb7

`tests/test_docs_hygiene.py`, five tests: non-ASCII outside an allowlist,
stale allowlist entries, mirrored test counts in load-bearing documents,
known-false architecture claims, and unresolvable `SPEC-NN` references.
It walks every markdown file in the repo except those under build and
vendor directories.

Both commits proved the guard could fail before it was accepted. The first
committed a probe containing an em-dash and showed the non-ASCII test
failing by name; the second put the probe under `mobile/`, which the
original walk could not see, and showed the widened walk catching it. A
guard that has never failed proves nothing, and a scope change that is
never exercised is indistinguishable from no change (R3).

The guard found `docs/research/SURVEY_FINDINGS.md` on its first run -- a
non-ASCII file that a hand-written audit of this repo had missed.

## Awaiting device verification

| SHA | Date | What | Verify with |
|-----|------|------|-------------|
| 21249f4 | Aug 9 | fix(dart): 4 compile errors plus lint warnings | `flutter analyze && flutter test` |
| 951f0ca | Aug 9 | feat(spec-07): wire typed signal methods to the UI | `flutter analyze && flutter test` |
| c6712bb | Aug 9 | fix(scripts): purge non-ASCII from all .ps1, add UTF-8 BOM | `.\scripts\smoke-test.ps1` |
| f778d8f | Aug 9 | feat(glossary): scripts/load_dish_glossary.py | run against live Supabase, then `--report-fk` |
| 1e0d999 | Aug 9 | fix(scripts): open data files as utf-8 | re-run the loaders on Windows |
| 10d27dd | Aug 9 | fix(venues): dict-wrapped JSON plus Laos vocabulary | see finding 1 below -- partly reverted |

`b47bce6` is documentation only and needs no verification.

## Known open issues

### High -- the venue loader cannot load the Laos data

The vocabulary expansion committed in `10d27dd` was reverted by the merge
`c5f64f3` twenty minutes later. On `main` today the VALID_* sets are back
to their pre-Laos state, so validating the three Laos files fails on
vocabulary for a large share of the 58 venues. Missing values include:

- categories: `street_food`, `walking_area`, `river_activity`, `craft_workshop`
- vibe tags: `photogenic`, `local_favourite`, `touristy`
- audiences: `solo`, `friends_group`, `seniors`, `mobility_limited`
- indoor_outdoor: `mixed`
- price bands: `mid`, `splurge`, `free`
- cuisines: `french_colonial`, `drink`

`FOOD_CATEGORIES` still lists `street_food`, which is no longer in
`VALID_CATEGORIES` -- the two sets disagree.

The data currently in Supabase was loaded before the revert, so the
database is fine and the script is not. Restoring the vocabulary is part
of the loader rewrite.

### High -- load_venues.py raises NameError without --geo-region

`file_geo_region` is read in the geo_region inference chain but is never
assigned. Every invocation that does not pass `--geo-region` explicitly
crashes, including the command printed in PROJECT_STATUS.md.

### High -- 145849d claim 2 did not land

That commit states `collect_warnings` was restored to
`{v.get("category") for v in venues}`. On `main` the line is still:

    cats = {v.get("opening_hours_structured") is None and v.get("opening_hours") is None}

So `"massage_spa" not in cats` is always true and every region is warned
as having zero massage_spa venues. The sibling fix in the same commit
(`startswith(f"{filepath}:")` instead of a substring match) did land.
A partial hunk landing on a non-ASCII file, the same failure mode that
left PROJECT_STATUS.md half-rebuilt. Do not trust that commit message.

### High -- halal plus pork passes the allergen check

There is no `LABEL_EXCLUDES_ALLERGENS` rule for halal, so a dish labelled
halal that contains pork validates cleanly. Safety hole for Muslim
travellers. Needs a rule plus a test.

### High -- venues_rag schema drift

The loader writes `typical_dwell_minutes`, `indoor_outdoor` and
`price_band` to `venues_rag`, and no migration defines those columns.
`name_local` and `nearest_landmark` are also absent, which is what blocks
SPEC-12 driver cards. A database rebuilt from `supabase/migrations/`
today fails on load.

### Medium -- hybrid_venue_search geo_region parameter

`supabase_service` passes a `geo_region` filter to the RPC, and the
function defined in `0001_initial_schema.sql` does not declare that
parameter. Either the live function has drifted from the migration or the
filter is silently ignored. Verify against the live database.

### Medium -- Supabase env var name mismatch

`scripts/load_venues.py` reads `TB_SUPABASE_URL` and `TB_SUPABASE_KEY`.
Parts of the documentation say `TB_SUPABASE_SERVICE_KEY`. Confirm which
name the settings layer expects and make all three agree.

### Medium -- opening_hours null on all 58 Laos venues

The loader field-name fix is committed but the data was never re-loaded,
so the scheduler has no hours to respect for any Laos venue.

### Low -- pytest floor is stricter than the code requires

`requirements-dev.txt` pins `pytest>=9.0.0`. That number came from a
misdiagnosis recorded below, not from the code. The only class the config
names is `PytestReturnNotNoneWarning`, which per the pytest changelog
exists from 7.2, was removed by accident in 8.4.0, and was reintroduced in
8.4.1. So exactly one release cannot parse the config and the accurate
floor is `>=8.4.1`. Harmless today, wrong tomorrow when it collides with
another pin.

### Low -- the guard walks .pytest_cache

`EXCLUDED_PARTS` does not list `.pytest_cache`, so a generated directory is
in scope. Its README is ASCII today and nothing fails, but a transient
artifact should not be able to redden the suite. Add it to the exclusions.

### Low -- mobility_limited overcorrected

Flagged on roughly two thirds of venues, which makes it useless as a
filter.

### Low -- VALID_DISH_CONTAINS lives in the wrong file

It sits in `scripts/load_dish_glossary.py` and belongs in
`config/dietary.py` (R5). Previously marked BLOCKED because
`config/dietary.py` contains em-dashes. It is no longer blocked: R14
documents the delete-and-recreate procedure, so `config/dietary.py` gets
rebuilt as pure ASCII with the constant moved in.

## Resolved

### Three nested READMEs were outside the guard -- fixed in 0053cb7

`mobile/README.md` (204 non-ASCII bytes), `scripts/README.md` (33) and
`supabase/migrations/README.md` (24) were invisible to the original walk.
The walk now covers the whole tree and all three are allowlisted.

## Retracted findings

### The pytest filterwarnings entry was not broken

A previous revision of this file recorded, as a Medium open issue, that
`pyproject.toml` referenced `PytestRemovedIn10Warning`, a class that does
not exist. That was wrong. pytest 9.1.1 defines it. The startup error came
from invoking the base compute's system pytest before installing the
project requirements, so it was an environment mistake reported as a repo
defect.

What survives is smaller and worth keeping. The config had:

    # PytestUnhandledCoroutineWarning removed in pytest 9.x; guard both versions.
    filterwarnings = [
        "ignore::pytest.PytestRemovedIn10Warning",
    ]

That comment describes the opposite of what the code does. Naming a class
in an ini `filterwarnings` entry is a hard dependency on the class
existing, so the entry written to guard both pytest versions was the sole
reason the older one could not start. It also only ever suppressed a
warning; it never enforced anything, so the R8 protection against an async
test silently becoming a no-op was never in this file.

The pytest changelog settles where that protection actually comes from.
Async tests without a handling plugin always fail, from 8.4 onward, with
no configuration required. Separately,
`PytestReturnNotNoneWarning` is a permanent warning that the maintainers
have explicitly decided will never become an error by default. The
replacement entry at `8b71949` promotes it to an error, which is worth
keeping on its own merits -- a test that returns instead of asserting
passes while proving nothing -- but it has nothing to do with coroutines.
The comment was corrected in `0053cb7`.

Cost of the misdiagnosis: one unnecessary config change and one
over-strict version pin, both made because a brief asserted a filter that
was not there and the executing agent matched the brief instead of
contradicting it.

## Tooling incidents

### runGit outage, Aug 11-12 2026 -- RESOLVED

A fresh session found `runGit` failing with `Git folder (Repo) has
invalid type` (`RESOURCE_DOES_NOT_EXIST`), after the previous session
died mid-task. The compute could still create files but could not delete,
move, or commit them, which blocks the entire R14 workaround.

Repair was a re-clone, not a retry. Notes for next time:

- The Databricks CLI allow-list refuses `repos delete`, and
  `workspace delete` is flagged as destructive. Recovery went through the
  Repos API instead.
- Re-cloning over the existing path fails with `RESOURCE_ALREADY_EXISTS`.
  The old Git folder has to be removed first.
- The replacement clone reports `git_cli_enabled: true`, `isClean: true`
  and `GIT_STATE_NORMAL`.

The re-clone also discarded six uncommitted files left by the dead
session, which was the intended outcome.

### __pycache__ writes are denied on the compute

The same filter that blocks all workspace writes (R15) also blocks
bytecode caching, so pytest fails on import until caching is disabled.
Run it there with `PYTHONDONTWRITEBYTECODE=1`.

### Half-landed documentation commit, 9fbe2f6

That commit rebuilt `PROJECT_STATUS.md` only partially, because R14
blocked the replacement of the em-dashed original. It left the new
summary prepended to the entire stale document, so the file asserted both
"8 signal types registered" and, further down, "Behavioral signals: NOT
STARTED". It also committed `PROJECT_STATUS.new.md` alongside it. Both
were resolved by rewriting the file through the GitHub API.

## Division of labour

Documentation and whole-file rewrites go through the GitHub API from the
planning side. The Databricks compute is reserved for code plus pytest.
This keeps documentation out of the R14 and R15 failure modes entirely.

## ASCII status of the documentation set

Enumerated from the full tree, not from a hand-written list. The earlier
version of this table was built by listing files from memory and missed
`docs/research/SURVEY_FINDINGS.md`. There are 27 tracked markdown files
and 18 contain non-ASCII bytes. All 18 are inside the guard's scan path
and allowlisted in `tests/test_docs_hygiene.py`. The allowlist may only
shrink.

Pure ASCII, editable in place with `editAsset`:

- `README.md`, `MASTER_BRD.md`
- `docs/PROJECT_STATUS.md`, `docs/AWAITING_VERIFICATION.md`,
  `docs/ENGINEERING_RULES.md`, `docs/TESTING_GUIDE.md`
- `docs/specs/SPEC-08-laos-venue-curation.md`,
  `docs/specs/SPEC-11-forced-choice-preferences.md`,
  `docs/specs/SPEC-12-show-driver-cards.md`

Non-ASCII. Each must be rebuilt rather than patched (R14):

| File | Non-ASCII bytes |
|------|-----------------|
| `docs/VISION.md` | 428 |
| `docs/DATA_MODEL_BRD.md` | 316 |
| `mobile/README.md` | 204 |
| `docs/research/survey_deep.md` | 137 |
| `docs/UX_BACKLOG.md` | 111 |
| `docs/specs/SPEC-04-offline-vault.md` | 78 |
| `docs/specs/SPEC-01-migrations-and-first-signal.md` | 65 |
| `docs/specs/SPEC-03-party-context.md` | 60 |
| `docs/specs/SPEC-07-signal-emission.md` | 48 |
| `docs/specs/SPEC-02-offline-queue-and-sync.md` | 47 |
| `docs/specs/SPEC-09-anonymous-identity.md` | 42 |
| `docs/research/survey_short.md` | 40 |
| `docs/specs/SPEC-06-behavioral-signals.md` | 38 |
| `scripts/README.md` | 33 |
| `docs/specs/SPEC-05-observability.md` | 24 |
| `supabase/migrations/README.md` | 24 |
| `docs/research/SURVEY_FINDINGS.md` | 6 |
| `docs/specs/SPEC-10-booking-anchors.md` | 6 |

Source files known to contain non-ASCII, same R14 constraint:

- `scripts/load_venues.py` (warning glyphs and an em-dash in output)
- `config/dietary.py` (em-dashes in comments)
- `config/regions.py` (box-drawing characters)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (em-dash)
- All Lao venue and glossary JSON files (Lao script, expected and correct)
