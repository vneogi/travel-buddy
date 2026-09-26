# Data Flywheel Operating Model

> Status: DECIDED DIRECTION. Not implemented.
>
> Recorded 24 Sep 2026. This document owns the end-to-end operating model
> for turning consented trip evidence into better decisions. It does not
> replace SPEC-17 (claims), SPEC-30 (outcomes), SPEC-43 (privacy/security),
> SPEC-20 (city onboarding), or SPEC-47 (internal review tooling).

## Moat statement

Travel Buddy learns which **feasible recovery decisions actually worked**
for travellers in specific places, at specific times, under specific
constraints, and improves later decisions using attributable, fresh,
validated evidence.

The asset is not submission volume. It is the combination of:

- a real decision context;
- a feasible set and the reasons candidates were included/excluded;
- the option shown and the option chosen;
- what happened afterward;
- explicit firsthand observations where the traveller chose to contribute;
- provenance, consent, freshness, conflict history, and review state.

A favourite is not proof a venue was open. A skipped stop is not a bad review.
An accepted swap is not proof it worked. A model summary is not verification.

## Stack decision

Keep Flutter, Riverpod, SQLite/outbox, FastAPI, Supabase/Postgres, and pgvector.

- Postgres is the system of record for trips, observations, claims, outcomes,
  review history, and versioned manifests.
- pgvector supports retrieval. It is not the fact store or adjudicator.
- No microservices, graph database, or second vector database for this loop.
- `trip_edge` is sufficient for route observations until measured query or
  scale evidence proves otherwise.
- The existing SQLite outbox transports allowed offline contributions with
  idempotency. It does not resolve conflicts or replan locally.

Before scale, strengthen the seams already named by SPEC-43 and SPEC-44:
atomic writes, idempotent commands, version/concurrency checks, production-
shaped Supabase tests, complete ownership, consent, deletion, and audit.

## Product boundary: a route, not a directory

The first density unit is the Vientiane - Vang Vieng - Luang Prabang corridor
and its real transfer/arrival moments. "Southeast Asia coverage" is not a
meaningful initial target.

Coverage includes more than venue count:

- day-start anchors and recovery alternatives;
- practical arrival and landmark information;
- hotel and locked booking context;
- inter-city transfer points and unknown transfer gaps;
- route-edge time/friction observations;
- offline-needed facts and their freshness;
- enough feasible alternatives for common failure modes.

Expansion waits for SPEC-13/20 and a versioned coverage gate. A town is not
"covered" because a JSON file has 40 rows.

## Four data planes

### 1. Private itinerary vault

Bookings, notes, exact dates, ordered itinerary, identity, party context, and
raw questions. Owner-scoped and never promoted into public guide data.

### 2. Behavioral outcome plane

Existing closed signals: candidate exposure, accept/reject, visited/skipped,
love, session start, arrival and observed edge duration. These describe what
happened in a private trip context.

They may support consented aggregate `derived_feature` values after SPEC-43.
They never become a venue fact one row at a time.

### 3. Explicit observation plane

A traveller deliberately answers one contextual question about a subject:

- "Was this entrance easy to find?"
- "Was it open when you arrived?"
- "Which transport mode did you actually use?"
- "Did this replacement work better for this situation?"

An observation is append-only, private-by-default review input. It is not
immediately rendered as truth.

Conceptual shape (migration number assigned only at implementation):

```text
observation(
  observation_id,
  subject_type, subject_id,
  attribute,
  observation_kind,
  value_json,
  observed_at,
  submitted_at,
  source_pseudonym,
  consent_purpose, consent_version,
  evidence_ref?,
  idempotency_key,
  review_status,
  withdrawn_at?,
  created_at
)
```

Closed `observation_kind`:

- `firsthand_fact`: a checkable, time/place-bound assertion;
- `experience`: subjective response, never resolved as objective fact;
- `route_outcome`: explicit report about a recommendation/edge, linked to
  the decision but not duplicating automatic signals.

Closed review states:

- `pending`
- `triaged`
- `needs_clarification`
- `accepted_as_claim`
- `disputed`
- `rejected`
- `withdrawn`

### 4. Public catalog and resolved claims

Externally sourced catalog identity plus SPEC-17 `attribute_claim` history.
An accepted observation may append a claim with a short attribute-specific
freshness horizon. It never overwrites the report or an older claim.

Resolved display is a pure function over claims. Models do not approve reports
or decide truth.

## Lifecycle

```text
feasible recommendation
  -> exposure recorded
  -> accept/reject
  -> later visited/skipped/outcome
  -> optional contextual observation
  -> idempotent ingest + consent/ownership check
  -> deduplicate/cluster for review
  -> accept, reject, clarify, or dispute
  -> append claim (if objective and supported)
  -> deterministic resolution + freshness
  -> reviewed catalog/pack release
  -> better feasible recommendation
```

Every transition is auditable. Withdrawal and deletion flow through raw
observation, evidence, contributor linkage, and derived outputs under SPEC-43.

## Contribution UX

### Ask at the useful moment

One small, skippable question after a relevant action, not a survey:

- after arrival: entrance/open status;
- after a route edge: transport mode or approximate observed duration;
- after replacement outcome: whether it solved the stated problem;
- at a stale, high-value claim: a SPEC-17 verification question.

Question selection uses:

```text
traveller value x claim importance x staleness x likely future readership
```

It shares the SPEC-22 interruption budget. Core itinerary use never requires
a contribution.

### Ask only answerable questions

Questions must be:

- firsthand;
- one action to answer;
- attributable to an exact subject;
- useful under a declared purpose;
- safe to skip;
- not already answered automatically by an existing signal.

Do not ask "Did you visit?" if `visited_confirmed` already captured it.
Do not infer "open" from a heart. Do not infer dislike from skip.

### Reciprocity

After submission:

- `Saved offline` or `Report saved`;
- `Being checked`;
- `Helped update this place`;
- `Reports conflict; the guide was not changed`;
- `Could not be used` with a short reason when appropriate.

Contributor status is private. No public profile, leaderboard, streak, or
points in the pilot. Rewards, if any, follow validated evidence, not taps
(SPEC-17).

## Provenance and freshness

Every observation answers:

- subject: venue, route edge, booking/transfer point, or decision;
- attribute and typed value;
- observed time vs submitted time;
- firsthand/imported/curated/derived source;
- consent purpose/version;
- evidence reference when permitted;
- review state and reviewer action;
- staleness horizon through the SPEC-17 registry;
- supersession/dispute history.

Evidence media is deferred until restricted storage, EXIF stripping, malware
scanning, deletion, access audit, and moderation are implemented. A photo
pipeline is not implied by the first observation table.

## Resolution rules

- Objective observations may become claims after review/corroboration.
- Subjective experience remains an aggregate or private history, never a fact.
- Behavioral outcomes feed derived features only above sample and consent
  thresholds.
- Safety-relevant claims follow SPEC-17's stricter official/refuse/defer rule.
- Conflicting reports coexist; resolution does not erase dissent.
- Expired evidence degrades display tier rather than silently disappearing.
- Sponsored rank remains separate from recommendation reason and claim truth.

## Data operations is part of the product

SPEC-47 owns a small internal workbench. Its job:

- queue and cluster new observations;
- identify likely duplicate subjects;
- show source, time, consent, evidence, and claim history;
- compare conflicts;
- accept/reject/clarify/dispute with reason codes;
- append/supersede claims without destructive edits;
- show stale/thin route coverage;
- publish reviewed, versioned packs/manifests.

No shared admin password, direct production-table editor, or model auto-
approval. Every reviewer action is attributed and reversible by another
append-only action.

## Versioned route/city packs

A pack is a derived release artifact, not a second hand-maintained database.

Manifest:

```text
pack_id
geo_regions[]
route_id?
schema_version
catalog_snapshot
claim_resolution_version
generated_at
freshness_summary
source/licence_summary
content_checksum
minimum_client_version
```

It contains public catalog facts and resolved claims only. No identity,
itinerary, observation source pseudonym, consent row, private note, or raw
behavior.

Initial packs may be API/cache snapshots rather than downloadable files. Do
not build a packaging subsystem before SPEC-13/20 and offline evidence require
one.

## Coverage and expansion gate

Before adding a route segment, record capability-specific coverage:

- sourced identity and external-ID coverage;
- current attributable operational claims;
- offline-needed field coverage;
- feasible alternatives by slot/day;
- transfer/arrival anchor coverage;
- unresolved conflict and stale-claim counts;
- last reviewed pack date.

No universal percentage is invented now. SPEC-47 records baselines during the
first pilot; thresholds are then fixed before the second route expansion.

Expansion also requires:

- SPEC-13 region/locale registry;
- SPEC-20 repeatable city kit;
- SPEC-21 licence position for OSM-derived packs;
- an owner for refresh/review;
- no city-specific code exception.

## Metrics

Primary moat metrics:

- attributable-current claim coverage for route-critical attributes;
- observation-to-reviewed-decision time;
- correction half-life (credible report to resolved display/pack);
- corroborated / disputed / rejected rates by attribute;
- percentage of recommendations with complete feasible-set and reason logs;
- accept -> visit/outcome linkage, not acceptance alone;
- replacement success for the stated constraint;
- fresh offline-needed coverage;
- contribution opt-in, skip, withdrawal, and deletion completion;
- active-trip and next-trip retention.

Guardrails:

- unsourced claim display rate;
- raw location leakage incidents;
- safety claim refusal rate;
- unresolved conflicts shown as fact;
- duplicate/out-of-owner submissions;
- moderator disagreement and reversal rate;
- sponsored results missing disclosure.

Submission count is diagnostic, not a north-star metric.

## Pilot

Prerequisites:

1. G0 owner reliability passed.
2. SPEC-43 applicable G1 gates passed.
3. SPEC-17 claim/attribute registry implemented.
4. SPEC-47 review queue live.
5. Question catalogue and consent purpose approved.
6. Withdrawal/deletion tested end to end.

Pilot is one narrow corridor and a few high-value attributes. Prompts are off
by default outside it. The first aim is to measure report quality and operation
cost, not maximize volume.

## Explicit non-goals

- Stack rewrite, microservices, graph database, second vector DB
- Model-verifies-model moderation
- Public reviews, comments, DMs, contributor profiles
- Background GPS or silent visit detection
- Selling/sharing location or behavioral profiles
- Gamification before abuse/quality evidence
- Automatic city expansion from report volume
- Treating raw reports as training data without separate purpose/consent
