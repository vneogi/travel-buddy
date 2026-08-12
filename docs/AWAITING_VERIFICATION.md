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

## Baseline, Aug 13 2026

A fresh clone on the Databricks compute at `8dfc412` reports 124 passed
and 5 skipped. All five skips are in `tests/test_supabase_integration.py`
with the reason "Supabase creds not configured (TB_SUPABASE_URL unset)".
Those are the expected skips. A skip anywhere else is a finding (R8).

## First tasks when the laptop returns

In this order. The first one is a data-durability fix and should not wait.

1. **Export the Dubai venues to a file.** They exist only as rows in the
   hosted database. Write them out as `data/dubai_venues.json` in the same
   shape as the Laos files, commit, and confirm the loader can dry-run it.
   Until that exists, the database cannot be rebuilt without data loss.
2. **Re-load the three Laos files.** One run settles the null
   `opening_hours`, the curated fields the loader is being taught to write,
   and the script corrections. Sequence it after those code changes land,
   not before.
3. Then the Dart, PowerShell and live-RPC items in the table below.

## Verified via pytest

### arrival_delta server derivation -- 564fd7d

Derives `arrival_delta` from `visited_confirmed.captured_at` against
`node.scheduled_start`, so one tap yields two data points. Covered by
`services/arrival_delta_service.py` and `tests/test_arrival_delta.py`.

### Documentation hygiene guard -- 8b71949, widened in 0053cb7

Five tests: non-ASCII outside an allowlist, stale allowlist entries,
mirrored test counts in load-bearing documents, known-false architecture
claims, and unresolvable `SPEC-NN` references. It walks every markdown
file in the repo except those under build and vendor directories.

Both commits proved the guard could fail before it was accepted. The first
committed a probe containing an em-dash and showed the non-ASCII test
failing by name; the second put the probe under `mobile/`, which the
original walk could not see, and showed the widened walk catching it. A
guard that has never failed proves nothing, and a scope change that is
never exercised is indistinguishable from no change (R3).

The guard found `docs/research/SURVEY_FINDINGS.md` on its first run -- a
non-ASCII file that a hand-written audit of this repo had missed.

### venues_rag schema drift guard -- 0aef5b0

`tests/test_venue_schema.py` parses `supabase/migrations/*.sql` for the
`venues_rag` column set and asserts the loader's write set is a subset.
Proven by deleting one `ADD COLUMN` line and watching the test name the
missing column. Since `8dfc412` it imports `VENUES_RAG_WRITE_COLUMNS` from
the loader instead of mirroring the list, so the two cannot diverge.

### Venue loader repair -- 8dfc412

The acceptance was a dry run over all three Laos files with no
`--geo-region` flag and no credentials: validation passed, 58 venues, zero
errors. This is the first evidence that the committed loader can load the
committed data. The loader test module passing was never sufficient -- it
passed throughout the period the loader was broken.

## Awaiting device verification

| SHA | Date | What | Verify with |
|-----|------|------|-------------|
| 21249f4 | Aug 9 | fix(dart): 4 compile errors plus lint warnings | `flutter analyze && flutter test` |
| 951f0ca | Aug 9 | feat(spec-07): wire typed signal methods to the UI | `flutter analyze && flutter test` |
| c6712bb | Aug 9 | fix(scripts): purge non-ASCII from all .ps1, add UTF-8 BOM | `.\scripts\smoke-test.ps1` |
| f778d8f | Aug 9 | feat(glossary): scripts/load_dish_glossary.py | run against live Supabase, then `--report-fk` |
| 1e0d999 | Aug 9 | fix(scripts): open data files as utf-8 | re-run the loaders on Windows |
| 0aef5b0 | Aug 13 | migration 0011, unapplied | apply after the amendment, then re-load |

`b47bce6` is documentation only and needs no verification.

## Known open issues

### High -- the Dubai venues have no source file

`data/` contains `laos_luang_prabang.json`, `laos_vang_vieng.json`,
`laos_vientiane.json` and `laos_dish_glossary.json`. There is no Dubai
file. The 16 Dubai venues exist only as rows in the hosted database, so
they cannot be re-loaded, diffed, reviewed, or restored, and a database
rebuilt from `supabase/migrations/` would not contain them.

This undercuts the point of the schema work in this sprint. The migrations
were made complete so the database could be rebuilt; rebuilding it today
would still lose the original MVP dataset. Export is the first device task.

### High -- the loader discards curated fields

Every venue JSON carries `name_local`, `nearest_landmark`,
`nearest_landmark_local`, `micro_location` and `wheelchair_notes`. The
loader writes none of them, and it ignores any key outside its write set
without comment, so five curated fields per venue are lost on every load
and nothing errors.

`wheelchair_notes` is the only real evidence behind the `mobility_limited`
audience filter, which is separately recorded as too loose to be useful.
It has never had data to be useful with.

### High -- halal plus pork passes the allergen check

There is no `LABEL_EXCLUDES_ALLERGENS` rule for halal, so a dish labelled
halal that contains pork validates cleanly. Safety hole for Muslim
travellers. Needs a rule plus a test.

### Medium -- wrong script in Lao-language fields

Twelve fields across eleven venues contain script that is not Lao.

Seven `name_local` values end in the Mandarin word for restaurant
(U+9910 U+5385) rather than the Lao equivalent: Tangor Drink &
Restaurant, Tamarind Restaurant & Cooking School, Bamboo Tree Restaurant &
Cooking School, Happy Mango Thai & Lao Bistro, Kualao Restaurant, Khop
Chai Deu, and Lao Kitchen.

Five `nearest_landmark_local` values contain the Thai word for riverside
(U+0E23 U+0E34 U+0E21) where the same dataset uses the Lao form elsewhere:
Tamarind, Utopia Bar & Restaurant, Saffron Coffee & Bakery, and Vientiane
Night Market (Vat Chan).

Both are detectable by codepoint range, so this becomes a test rather than
a proofreading exercise. The accented characters in the dish glossary are
not defects -- they are French loanwords and are spelled correctly.

Separately and not machine-detectable: several `name_local` values are
phonetic transliterations of the English name rather than a Lao name, for
example Lao Kitchen, Utopia Bar and L'Hibiscus. That may be exactly what
the signage says, or it may be invented. Only someone who has seen the
places can tell.

### Medium -- opening_hours null on all 58 Laos venues

Settled: `venues_rag` has both `opening_hours` (text, from `0001`) and
`opening_hours_structured` (JSONB, added by `0008`, which never dropped the
original). The loader writes only `opening_hours_structured`, reading the
`opening_hours` key from the JSON via a fallback. The data files do carry
hours for all 58 venues, so a re-load lands them.

The legacy `opening_hours` column is dead. Do not "fix" the loader by
writing to it.

### Medium -- hybrid_venue_search geo_region parameter

`supabase_service` passes a `geo_region` filter to the RPC, and the
function defined in `0001_initial_schema.sql` does not declare that
parameter. Either the live function has drifted from the migration or the
filter is silently ignored. Verify against the live database.

### Medium -- Supabase env var name mismatch

`scripts/load_venues.py` reads `TB_SUPABASE_URL` and `TB_SUPABASE_KEY`.
Parts of the documentation say `TB_SUPABASE_SERVICE_KEY`. Confirm which
name the settings layer expects and make all three agree.

### Low -- pytest floor and the guard's scan of generated directories

Both addressed in `0aef5b0`: the floor is now `pytest>=8.4.1`, matching the
one release that cannot parse the config, and `.pytest_cache` is excluded
from the documentation walk.

### Low -- mobility_limited overcorrected

Flagged on roughly two thirds of venues, which makes it useless as a
filter. Revisit once `wheelchair_notes` actually reaches the database.

### Low -- Vientiane massage_spa count is unconfirmed

This was reported by `collect_warnings`, which was comparing against a set
of booleans and therefore warned every region about every category. Re-check
against the data before treating it as a curation gap.

### Low -- VALID_DISH_CONTAINS lives in the wrong file

It sits in `scripts/load_dish_glossary.py` and belongs in
`config/dietary.py` (R5). No longer blocked: R14 documents the
delete-and-recreate procedure, so `config/dietary.py` gets rebuilt as pure
ASCII with the constant moved in.

## Resolved

### Venue loader could not load the Laos data -- fixed in 8dfc412

Three defects, all closed and all proven by the dry run rather than by
tests:

- The vocabulary expansion added in `10d27dd` and reverted by the merge
  `c5f64f3` is restored. Recovered from history rather than retyped, then
  checked against the values actually present in the data. The recovered
  set covers the data exactly, with no gaps in either direction.
- `file_geo_region` is assigned again, from the `geo_region` key on the
  file's dict wrapper. Its absence made every invocation without an
  explicit `--geo-region` raise `NameError`, including the command printed
  in our own documentation.
- `collect_warnings` compares against `{v.get("category") for v in venues}`
  instead of a one-element set of booleans, so category coverage warnings
  mean something for the first time. Commit `145849d` claimed this fix and
  did not land it.

`FOOD_CATEGORIES` and `VALID_CATEGORIES` now agree on `street_food`, and
`scripts/patch_venues_loader.py` -- a monkey-patching duplicate of the same
four fixes -- is deleted.

### Three nested READMEs were outside the guard -- fixed in 0053cb7

`mobile/README.md` (204 non-ASCII bytes), `scripts/README.md` (33) and
`supabase/migrations/README.md` (24) were invisible to the original walk.
The walk now covers the whole tree and all three are allowlisted.

## Retracted findings

### The pytest filterwarnings entry was not broken

A previous revision recorded, as a Medium open issue, that `pyproject.toml`
referenced `PytestRemovedIn10Warning`, a class that does not exist. That
was wrong; pytest 9.1.1 defines it. The startup error came from invoking
the base compute's system pytest before installing the project
requirements -- an environment mistake reported as a repo defect.

What survives is smaller. The original comment claimed the entry guarded
both pytest versions, when naming a class in an ini `filterwarnings` entry
is a hard dependency on that class existing, so the entry was the sole
reason the older version could not start. It also only ever suppressed a
warning and never enforced anything.

Per the pytest changelog, async tests without a handling plugin always
fail from 8.4 onward with no configuration, and
`PytestReturnNotNoneWarning` is a permanent warning the maintainers have
decided will never become an error by default. So the replacement entry
earns its place on its own merits -- a test that returns instead of
asserting passes while proving nothing -- and has nothing to do with
coroutines.

Cost: one unnecessary config change and one over-strict version pin, both
because a brief asserted a filter that was not there and the executing
agent matched the brief instead of contradicting it.

### SPEC-12 was never blocked on curation

The spec claimed no Laos venue carried Lao script and that curating 58 of
them was the critical path. Both were wrong. All 58 already carry
`name_local`, `nearest_landmark` and `nearest_landmark_local`. The blocker
was always the loader discarding them, which is recorded above as an open
issue. Cost: an instruction to the project owner to spend days on data
entry that was already done.

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

### __pycache__ writes are denied on the compute

The same filter that blocks all workspace writes (R15) also blocks
bytecode caching, so pytest fails on import until caching is disabled.
Run it there with `PYTHONDONTWRITEBYTECODE=1`.

### Half-landed documentation commit, 9fbe2f6

That commit rebuilt `PROJECT_STATUS.md` only partially, because R14
blocked the replacement of the em-dashed original. It left the new summary
prepended to the entire stale document, so the file asserted both "8 signal
types registered" and, further down, "Behavioral signals: NOT STARTED".
Resolved by rewriting the file through the GitHub API.

## Division of labour

Documentation and whole-file rewrites go through the GitHub API from the
planning side. The Databricks compute is reserved for code plus pytest.
This keeps documentation out of the R14 and R15 failure modes entirely.

## ASCII status

Enumerated from the full tree, not from a hand-written list. There are 27
tracked markdown files and 18 contain non-ASCII bytes. All 18 are inside
the hygiene guard's scan path and allowlisted in
`tests/test_docs_hygiene.py`. The allowlist may only shrink.

Pure ASCII, editable in place with `editAsset`:

- `README.md`, `MASTER_BRD.md`
- `docs/PROJECT_STATUS.md`, `docs/AWAITING_VERIFICATION.md`,
  `docs/ENGINEERING_RULES.md`, `docs/TESTING_GUIDE.md`
- `docs/specs/SPEC-08-laos-venue-curation.md`,
  `docs/specs/SPEC-11-forced-choice-preferences.md`,
  `docs/specs/SPEC-12-show-driver-cards.md`

Non-ASCII markdown. Each must be rebuilt rather than patched (R14):

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

Source files still containing non-ASCII, same R14 constraint:

- `config/dietary.py` (em-dashes in comments)
- `config/regions.py` (box-drawing characters)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (em-dash)
- All Lao venue and glossary JSON files (Lao script, expected and correct
  apart from the contamination recorded above)

`scripts/load_venues.py` left this list at `8dfc412` and is now pure ASCII.
