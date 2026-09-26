# SPEC-47: Data Operations Workbench

> Status: SPECIFIED. Not implemented.
>
> Depends on SPEC-43 for identity, consent, ownership, deletion, logging,
> abuse and admin access; SPEC-17 for append-only claims, attribute registry,
> resolution and staleness; SPEC-13/20 for region and city-pack operations.
> Operating model: `docs/DATA_FLYWHEEL_OPERATING_MODEL.md`.
>
> This is an internal product. It is not a traveller social network and not
> a direct SQL editor.

## Goal

Give a small trusted operations team one safe workflow to turn explicit,
consented traveller observations and sourced updates into reviewed claims and
coverage decisions without erasing history or editing production rows by hand.

The workbench is a prerequisite for enabling contribution prompts in a
non-owner route pilot. The first non-owner build may exist with contribution
prompts disabled after SPEC-43; the prompts do not turn on until this review
path exists.

## Why this is moat infrastructure

Collection without adjudication creates a spam database. Claims without
operations become stale. A city pipeline without coverage visibility creates
shallow expansion. The workbench is where trust, freshness, route depth, and
correction speed become operational rather than aspirational.

## Architecture decisions

1. **Same stack.** Protected Flutter/Web or simple server-rendered internal UI
   over FastAPI/Postgres. No microservice, graph DB, or second vector store.
2. **Admin identity is real identity.** Server-issued account, MFA where the
   provider supports it, role/claim checked server-side, short session, access
   log. No shared secret header or hidden URL.
3. **No direct table editor.** Every action calls a typed command and appends
   an audit event.
4. **Reports are not claims.** A pending observation cannot appear on a
   traveller screen. Acceptance appends an `attribute_claim`; it does not
   update `venues_rag` in place.
5. **Models may cluster, never adjudicate.** A model/embedding can suggest
   duplicates after SPEC-43 egress approval. A human reviews the evidence and
   owns the action.
6. **Postgres remains canonical.** pgvector may aid duplicate search. Vector
   similarity is not identity resolution or confidence.
7. **Both persistence paths.** Any interface addition is implemented in the
   in-memory and Supabase backends (R4), with production-shaped hosted tests.

## Data contracts

### Observation

Use the append-only shape in the flywheel operating model. Required:

- stable `observation_id`;
- subject type/id;
- registered attribute;
- closed observation kind;
- typed value;
- observed/submitted timestamps;
- consent purpose/version;
- idempotency key;
- review status;
- source pseudonym that is resolvable for rights handling but not shown to
  another contributor.

Unknown subject/attribute is refused into a quarantine queue, not attached to
the nearest venue.

### Review action

```text
observation_review_event(
  event_id,
  observation_id,
  action,
  reason_code,
  reviewer_id,
  note?,
  previous_status,
  next_status,
  created_at
)
```

Closed actions:

- `triage`
- `request_clarification`
- `accept_as_claim`
- `mark_disputed`
- `reject`
- `withdraw`
- `reverse_prior_action`

Reviewer notes are private operational data, redacted in exports, and covered
by retention/access policy.

### Coverage snapshot

```text
coverage_snapshot(
  snapshot_id,
  route_or_region,
  pack_id?,
  metric_key,
  numerator,
  denominator,
  computed_at,
  method_version
)
```

Metrics are recomputable and versioned. No hand-entered green status.

## MVP screens

### 1. Inbox

- pending and needs-clarification queues;
- filter by route, subject, attribute, age, conflict, evidence presence;
- SLA age;
- no exact contributor itinerary.

### 2. Subject history

- catalog identity/external IDs;
- all observations for the attribute;
- existing claims and resolved value/tier/as_of;
- conflict timeline;
- source and consent eligibility;
- freshness horizon.

### 3. Review action

- accept, reject, clarify, dispute;
- required closed reason code;
- preview of the claim that acceptance will append;
- explicit confirmation;
- resulting traveller-facing tier/copy preview through the real resolver.

### 4. Duplicate/mismatch queue

- candidates by external identity first, normalized name/coordinate second,
  vector suggestion last;
- reviewer merges references or rejects the suggestion;
- no automatic venue merge.

### 5. Route coverage

- current attributable claim coverage by critical attribute;
- stale/expiring claims;
- unresolved conflicts;
- offline-needed fields;
- feasible alternatives by named slot/day;
- transfer/arrival gaps;
- last pack release.

### 6. Pack release

- generate from resolved public claims and catalog snapshot;
- show licence/source summary and freshness warnings;
- immutable manifest + checksum;
- two-person approval before a non-owner production release once more than
  one operator exists;
- rollback points to a previous pack; it never rewrites history.

## Traveller reciprocity endpoint

Authenticated, owner-only:

```text
GET /user/observations
```

Returns the caller's contribution status:

- saved;
- being checked;
- clarification requested;
- helped update;
- conflict/no change;
- withdrawn/rejected with safe reason.

It never reveals another contributor or internal reviewer notes.

Clarification is a new explicit prompt and shares the interruption budget. It
does not open a free-text moderator chat in v1.

## Consent, rights, and deletion

- Contribution purpose is separate from necessary trip operation,
  analytics, personalization, location, and marketing.
- No prompt or outbox row before the choice required by SPEC-43.
- Withdrawal deletes unsent observations immediately and queues the rights
  request offline.
- Server withdrawal prevents unresolved observation use and marks accepted
  person-linked claims for rights review. Public facts with an independent
  lawful source may remain only after contributor linkage/evidence is removed
  or replaced under the documented policy.
- Derived features and packs carry lineage so deletion can recompute or
  invalidate them.
- Evidence media, if later enabled, has its own restricted store and deletion
  receipt.

## Conflict and corroboration

- Two agreeing taps are not automatically independent evidence if they share
  identity/device/party or copy the same imported source.
- Corroboration requires independent sources under SPEC-17.
- A conflict lowers the resolved tier or marks the claim disputed according to
  the pure resolver. It does not trigger majority vote.
- Safety-relevant facts cannot be promoted by traveller count alone.
- Reviewer action cannot manufacture a source stronger than the evidence.

## Abuse controls

- Per-identity, subject, location-area and time-window limits.
- Idempotency prevents offline retry duplication.
- Ownership checks on trip/decision-linked submissions.
- Anomaly queue for impossible travel/time, burst submissions, repeated
  reversals, and collusion indicators.
- No public score that rewards volume.
- Contributor weight is a derived feature with method version and minimum
  history; it never bypasses source/safety rules.

## Observability

Track:

- queue age and correction half-life;
- accept/reject/dispute/clarify rates;
- reviewer reversals and disagreement;
- duplicate rate;
- stale critical claims;
- observation/claim/pack lineage failures;
- rights requests and completion;
- unauthorized admin attempts.

Logs contain IDs, action codes and request IDs, not evidence text, raw
location, booking references, or private notes.

## Tests

- Non-admin cannot read or mutate any workbench route.
- Admin action is owner-attributed and append-only.
- Direct status/claim overwrite is impossible through the API.
- Offline duplicate submission with one idempotency key yields one observation.
- Accept appends one claim and preserves the observation and prior claims.
- Reversing acceptance appends review/claim history; it does not delete.
- Subject mismatch goes to quarantine, never nearest-name attachment.
- Resolve preview equals the production resolver output.
- Contributor endpoint returns only caller-owned rows and no reviewer notes.
- Consent withdrawal blocks unresolved use and invalidates/recomputes lineage.
- Pack contains no identity, pseudonym, trip, consent, raw observation, or
  behavioral payload.
- Supabase RLS/authorization tests use two users and one admin against hosted-
  shaped PostgreSQL, not only the in-memory backend.

## Acceptance

- A submitted observation can be followed from ingest to review to claim to
  resolved value to pack manifest.
- Every transition is attributable and non-destructive.
- A conflict is visible and cannot silently resolve to `assert`.
- A traveller sees an honest private status for their report.
- Operations can identify the thinnest/stalest corridor fields.
- Withdrawal/deletion reaches observations, evidence, derived values and packs.
- Contribution prompts remain disabled until the workbench and SPEC-43 gates
  pass.

## Non-goals

- Public moderation, reviews, comments, DMs, leaderboards
- Model approval or automatic truth resolution
- Generic CMS or arbitrary database editing
- Contributor payments/rewards
- New city scraping
- Full offline pack downloader
- Graph database or microservices
