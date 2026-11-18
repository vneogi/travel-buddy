# Document map -- how to resume

> This file is the index, not a second status report.
> Recorded 11 Oct 2026 so a pause, a new agent, or a compacted context
> does not require rereading chat, canvases, or every brainstorming memo.

Chat, transcripts, Cursor canvases, and agent summaries are working memory.
If a decision is not routed here, it is not a decision.

## Resume in this order

1. This file -- who owns which question, what is not canonical.
2. `WAYS_OF_WORKING.md` and `ENGINEERING_RULES.md` -- how people and code behave.
3. `HANDOFF_PLANNING_AGENT.md` -- Now / Next / Later and do-not-reopen.
4. `PROJECT_STATUS.md` -- shipped vs specified vs declined, and risks.
5. Only the canonical documents linked for the work you are about to do.
6. Compare the handoff's application SHA and docs SHA with `origin` before
   changing anything.

Do not start with a full-repo archaeology, a canvas, or a transcript. If two
documents disagree, follow Precedence below and name the conflict in
`PROJECT_STATUS.md` until the owning document is updated.

## Continuity state on 17 Nov 2026

- New to the repo? Read `README.md`, then `VISION.md` section 0 (what the
  app is, who it serves, what it does today, why it is different).
- GitHub `main` was at `a147acf` (PR #280) when this was written; check
  `git log` for newer work.
- Landed since 25 Oct: SPEC-43 Gap 4 erase / export slices, retention R1 planner (PR #295), and the durable
  tombstone; Stone Town and Nungwi packs (hosted); F2 Swahili-first driver
  card order; F3 existing-trip date markers; the What Now chat fix
  (PR #260); SPEC-53 situation chips; SPEC-56 offline readiness row;
  SPEC-49 Show-to-driver; SPEC-48 NOW / UP NEXT strip; SPEC-50 swap
  comparison; SPEC-52 markers; the Isochrones provider (slice 2 flag off);
  SPEC-57 Arrival Armor slice 1.
- Hosted: migrations through 0027; Cloud Run revision and env names in
  `HOSTED_STATE.md`.
- Owner focus: the Tanzania trip (Stone Town 26-28 Dec 2026, Nungwi 29 Dec
  2026 to 2 Jan 2027). Owner device pause from 16 Nov for about four days;
  phone checks for SPEC-49, 48, 50, 52 and 57 are batched for the return.
- Genie queue and the single open-items list: `PROJECT_STATUS.md`
  "Open items, 2026-11-15 to 2026-12-04".
- Unchanged guardrails: the traveller confirms every mutation; SPEC-43
  gates non-owner distribution; live LLM processing of personal trips is
  not enabled; no new city outside the SPEC-13 / SPEC-20 factory.

The 25 Oct checkpoint (Gap-by-Gap SHA ledger) is superseded; that history is
in `PROJECT_STATUS.md`, `RELEASE_READINESS.md` and `git log`.

Refresh this section at the next continuity checkpoint. Do not let it become
a second PROJECT_STATUS.

## Precedence

When documents collide, use this order. A lower row does not override a higher
one by being newer in chat.

1. `ENGINEERING_RULES.md` -- how code and tests must behave.
2. The numbered spec that owns the capability.
3. The operating or strategy document that owns the question (table below).
4. `HANDOFF_PLANNING_AGENT.md` -- sequence for this week, not product law.
5. `PROJECT_STATUS.md` -- what is built; not a design substitute.
6. Dated device facts -- `AWAITING_VERIFICATION.md` only.
7. A brief -- one-shot execution instruction; stale after the PR lands.
8. `MASTER_BRD.md`, `DATA_MODEL_BRD.md`, canvases, research notes, transcripts.

Later specs already win over older BRD language: SPEC-43 over identity/consent
wording in `DATA_MODEL_BRD.md`; SPEC-44 over recommendation/memory wording
there. VISION Part III is not committed.

## Canonical owners -- one question, one document

| Question | Owner |
|---|---|
| What is built, what is next, known risks | `PROJECT_STATUS.md` |
| What the planning agent must not reopen this week | `HANDOFF_PLANNING_AGENT.md` |
| How agents, owner, and evidence work | `WAYS_OF_WORKING.md` |
| Rules earned from defects | `ENGINEERING_RULES.md` |
| What the product is and is not; moat thesis; deferred ideas | `VISION.md` |
| Plain-language product summary: capabilities, users, USPs | `VISION.md` section 0 (README carries the short version) |
| Which traveller, which cities, Banana Pancake order | `MARKET_STRATEGY.md` |
| Owner-only vs non-owner vs store | `RELEASE_READINESS.md` |
| How consented evidence becomes reviewed claims | `DATA_FLYWHEEL_OPERATING_MODEL.md` |
| What a stranger-facing surface needs on client vs server | `CONSUMER_SURFACE_ROADMAP.md` |
| Schema and data-layer sequence | `DATA_LAYER_ROADMAP.md` |
| Hosted migrations and credential-backed providers | `HOSTED_STATE.md` |
| Dated device / laptop / SQL observations | `AWAITING_VERIFICATION.md` |
| Signed APK how-to | `ANDROID_BUILD.md` |
| Cloud Run deploy without wiping env vars | `CLOUD_RUN_DEPLOY.md` |
| Phone and laptop test procedures | `TESTING_GUIDE.md` |
| OSM coverage measurement (dated) | `CORRIDOR_COVERAGE.md` |
| Screen ideas that were accepted or rejected | `UX_BACKLOG.md` |
| Signal/schema concepts (yields to later specs) | `DATA_MODEL_BRD.md` |
| Technical system description, not status | `MASTER_BRD.md` |
| A capability's contract, remainders, and acceptance | the matching file under `docs/specs/` |
| A single Genie implementation slice | `docs/briefs/` (historical after merge) |

Do not add a ninth strategy memo for a question that already has a row.
Amend the owner, or record a rejected alternative in that owner.
The 25 Oct 2026 external travel-strategy memo is adjudicated in
`HANDOFF_PLANNING_AGENT.md` plus VISION, MARKET_STRATEGY,
DATA_FLYWHEEL, and RELEASE_READINESS. The Google Doc is not
canonical.

## Spec clusters -- read the cluster, not the archive

Use `PROJECT_STATUS.md` for DONE / PARTIAL / SPECIFIED. This list is only
which specs belong together so a new session does not reopen the wrong era.

**October field spine (largely on main).** SPEC-01 through SPEC-10, SPEC-12,
SPEC-16, SPEC-22, SPEC-30, SPEC-31, SPEC-32, SPEC-35 through SPEC-38,
SPEC-40, SPEC-41 Phase A, SPEC-45 Phase A, SPEC-44 Phase A,
SPEC-46 Phase A.

**Specified remainders on that spine.** SPEC-46 Phase A (`d1df944`),
thin typed Ask-to-Add (`0344b4b`), thin typed Move (`e51513e`),
empty-day catalog Add (`b6ddecf`), and trip-private uncatalogued Add
(`05d917e`), SPEC-43 Gap 1 (`2460edf`), and SPEC-43 Gap 6
(`c65261c`), SPEC-43 Gap 2 (`0b8125f`), SPEC-43 Gap 9
(`163a14c`), Gap 9 closed schemas (`fb72545`), SPEC-43 Gap 12
HTTPS (`6f1dab8`), and Gap 12 cache keys (`290f821`), Gap 12
chat URLs (`14ce56d`), and Gap 12 ATS (`be89128`), and Gap 12
trip-route ownership (`f486079`) are on main;
Gap 11 body/depth (`2077d8d`, PR #119) is on main;
Gap 9 GPS (`08253cb`, PR #122) is on main;
Gap 9 derived metadata (`4265403`, PR #125) is on main;
Gap 11 rate (`c70296c`, PR #128) is on main;
Gap 11 spend (`e7c89b5`, PR #131) is on main;
Gap 10 422 stripping (`04169f9`, PR #134) is on main;
Gap 8 HMAC (`5a9f684`, PR #137) is on main;
Gap 8 canaries (`895045a`, PR #140) is on main;
Gap 8 trip/date/source-version (`606626e`, PR #142) is on main;
Gap 8 active purge (`8fab43b`, PR #145) is on main;
SPEC-42 unknown-time
excursions stay later;
trip-optional and production-LLM SPEC-25; SPEC-10 HITL reflow;
SPEC-29 weather-day detail; SPEC-44 A4/A5 and Flutter command queue.
SPEC-46 Phase B GPS waits for SPEC-43.

**November UI/UX package (Nov 2026).** SPEC-48 through SPEC-56, from
`docs/briefs/UI_UX_IMPLEMENTATION_SPECS_2026-11-15.md`. Slices on main:
SPEC-53, SPEC-56, SPEC-49 Show-to-driver, SPEC-48 strip; SPEC-52 markers
(as F3); SPEC-50. SPEC-51, SPEC-54, SPEC-55 designed and parked until
after the December trip. **Moonshot triage (2026-11-17):** VISION
section 32; thin Arrival Armor is SPEC-57 (slice 1 on main, PR #292); Party
Tether declined; Point & Settle mostly declined; Whisper and Passport
Phase 2; Route Deviation Phase 3.

**Release and non-owner gates.** SPEC-43, then SPEC-09 remainder / SPEC-24 /
SPEC-27 as called by SPEC-43 and RELEASE_READINESS.

**Governed evidence and city factory (post-Laos, ordered).** SPEC-13, SPEC-17
minimum claim store, observation lifecycle in the flywheel model, SPEC-44
decision capture, SPEC-47 workbench, then SPEC-20 packs. Bangkok is the
factory proof; Chiang Mai / Pai follow. Learned influence stays zero until
the flywheel model's evidence gates pass.

**Specified, not this season unless the owner changes the sequence.** SPEC-11,
SPEC-15, SPEC-18, SPEC-19, SPEC-21, SPEC-23, SPEC-26 remainder, SPEC-28,
SPEC-34, SPEC-39. PDF (SPEC-39) and inspiration (SPEC-28) stay
deferred. SPEC-14 dietary claims are retired.

**Declined or shrunk in the owner documents, not in chat.** Full Offline Vault
and Hotel Rescue shortcut (SPEC-04 / UX_BACKLOG); Gmail OAuth; Isar; HealthKit;
LangGraph as product; graph DB / extra vector DB / microservices for the moat;
Party Tether BLE mesh and camera dietary "safe for party" claims (VISION
section 32 / UX_BACKLOG Nov 17 moonshot triage).

## What a brainstorming session is allowed to become

Every session must land in exactly one of:

1. **Accepted** -- amend the owning document in the table above. If it is a
   new capability, add a spec and a PROJECT_STATUS row, then add the spec to
   the correct cluster here.
2. **Rejected** -- record the rejection and rationale in the owning document
   (VISION deferred table, UX_BACKLOG, HANDOFF "already adjudicated", or the
   spec's non-goals). Do not leave the "no" only in chat.
3. **Pending** -- name the open decision in `PROJECT_STATUS.md`. Do not create
   a new top-level memo to hold an undecided idea.

Never create a parallel document that restates VISION, MARKET_STRATEGY, or
the flywheel model "from a new angle." Link and amend.

Briefs are for Genie execution. They do not own strategy. After merge, status
lives in PROJECT_STATUS / HOSTED_STATE / AWAITING_VERIFICATION; the brief is
archive.

Canvases may visualize a stocktake. They are not the record. If the canvas
disagrees with this map or the handoff, the documents win.

## Continuity checkpoint

Required at planned handoff, likely context compaction, or the end of a
decision-heavy session (`WAYS_OF_WORKING.md` section 10):

- Route every accepted / rejected / pending item as above.
- Update HANDOFF Now / Next / Later and the Pause state section here.
- Commit and push the documentation branch.
- Say whether GitHub `main` actually has those commits.

A new agent that follows Resume above, without the previous transcript, is
the test that this file is doing its job.