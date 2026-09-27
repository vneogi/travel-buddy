# Document map -- how to resume

> This file is the index, not a second status report.
> Recorded 27 Sep 2026 so a pause, a new agent, or a compacted context
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

## Pause state on 27 Sep 2026

- Application `main`: `9a7b9d9` (SPEC-44 Phase A).
- Docs branch: `docs/pre-laos-final-state` (this map and living-doc updates).
  Not on GitHub `main` until that branch is merged.
- Hosted: migrations through 0025; Cloud Run `travel-buddy-00012-8wv`.
- Freeze APK SHA256 `bd935bf2...`. Thursday 1 Oct: preload the real trip,
  airplane reopen. Do not start SPEC-42 Add/Move, SPEC-46, a new city, PDF,
  or polish this week.
- After return: Ask history, place prompts, weather-day detail, hotel-as-Flight,
  then the post-Laos sequence in `HANDOFF_PLANNING_AGENT.md`.

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

## Spec clusters -- read the cluster, not the archive

Use `PROJECT_STATUS.md` for DONE / PARTIAL / SPECIFIED. This list is only
which specs belong together so a new session does not reopen the wrong era.

**October field spine (largely on main).** SPEC-01 through SPEC-10, SPEC-12,
SPEC-16, SPEC-22, SPEC-30, SPEC-31, SPEC-32, SPEC-35 through SPEC-38,
SPEC-40, SPEC-41 Phase A, SPEC-45 Phase A, SPEC-44 Phase A.

**Specified remainders on that spine.** SPEC-10 HITL reflow; SPEC-25 durable
Ask history, place prompts, trip-optional Ask; SPEC-29 weather-day detail;
SPEC-42 Add/Move; SPEC-44 A4/A5 and Flutter command queue.

**Release and non-owner gates.** SPEC-43, then SPEC-09 remainder / SPEC-24 /
SPEC-27 as called by SPEC-43 and RELEASE_READINESS.

**Governed evidence and city factory (post-Laos, ordered).** SPEC-13, SPEC-17
minimum claim store, observation lifecycle in the flywheel model, SPEC-44
decision capture, SPEC-47 workbench, then SPEC-20 packs. Bangkok is the
factory proof; Chiang Mai / Pai follow. Learned influence stays zero until
the flywheel model's evidence gates pass.

**Specified, not this season unless the owner changes the sequence.** SPEC-11,
SPEC-15, SPEC-18, SPEC-19, SPEC-21, SPEC-23, SPEC-26 remainder, SPEC-28,
SPEC-34, SPEC-39, SPEC-46. PDF (SPEC-39) and inspiration (SPEC-28) stay
deferred. SPEC-14 dietary claims are retired.

**Declined or shrunk in the owner documents, not in chat.** Full Offline Vault
and Hotel Rescue shortcut (SPEC-04 / UX_BACKLOG); Gmail OAuth; Isar; HealthKit;
LangGraph as product; graph DB / extra vector DB / microservices for the moat.

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
