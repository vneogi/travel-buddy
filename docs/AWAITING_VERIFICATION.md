# Awaiting Verification

Consolidated Aug 14 2026. This file is a dated log of what cannot be verified
from a keyboard, plus the findings that were retracted and the tooling
incidents worth not repeating. It is the only place in the repo where dated
observations belong (R16).

What it deliberately does not carry: the device-day task order, which lives in
`docs/PROJECT_STATUS.md`. Two documents holding the same ordered list is how
they end up contradicting each other, which is what this consolidation is
fixing.

Commits are identified by SHA only. Earlier revisions numbered work as `#84`,
`#85` and so on; those numbers cannot be reconciled against `git log`.

## What cannot be verified without a device or credentials

| Area | Unverified since | Verify with |
|---|---|---|
| Migrations 0011 to 0018 | committed, never applied | apply against the live database, in order |
| The five Supabase tests | never once executed | run the suite with `TB_SUPABASE_URL` set |
| Flutter client | Aug 9 | `flutter analyze && flutter test` on a device |
| PowerShell scripts | Aug 9 | `.\scripts\smoke-test.ps1` on Windows |
| `hybrid_venue_search` geo_region parameter | unknown | compare the live function against `0001` |
| Dubai row contents, including AED magnitudes | never | read them while connected |
| `pg_description` non-ASCII | never | scan directly; no file guard can see the database |

The Supabase row is the largest single gap in the repo. Every claim about the
Supabase write path currently rests on `FakeClient` doubles. R8 treats a
permanent skip as a finding, and this is the oldest one.

## Open issues that need a person, not a test

### High -- the Dubai venues have no source file

`data/` holds the three Laos venue files and the dish glossary. There is no
Dubai file. Those venues exist only as rows in the hosted database, so they
cannot be re-loaded, diffed, reviewed or restored, and a database rebuilt from
`supabase/migrations/` would not contain them. Exporting them is the first
device task for that reason: it is a data-durability fix, not a convenience.

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

### Low -- VALID_DISH_CONTAINS lives in the wrong file

It sits in `scripts/load_dish_glossary.py` and belongs in `config/dietary.py`
(R5). No longer blocked by anything; R14 and R15 were rewritten and the
delete-and-recreate procedure they once required is retired.

## Closed since the last revision

Recorded because each was open long enough to be quoted elsewhere, and a reader
finding a stale copy of this file should be able to tell.

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
