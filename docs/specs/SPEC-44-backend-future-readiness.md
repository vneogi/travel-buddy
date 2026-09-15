# SPEC-44: Backend Integrity and Future-Readiness Foundation

> Status: SPECIFIED. Not implemented.
>
> Sequence: SPEC-41 A3b is complete at reviewed branch head `7f25042`. Finish
> the remaining Laos reliability tranche: SPEC-10 provider-aware paste,
> SPEC-25 grounded trip-scoped Ask, and the resulting hosted API / signed APK
> verification. Then implement this spec's integrity phase before normalized
> itinerary reads, multiple devices, or a second real city. SPEC-43 remains
> the release gate before any non-owner distribution or production LLM
> processing of personal trip data.
>
> This is an umbrella architecture contract. It does not replace SPEC-13
> (region registry), SPEC-16 (normalized itinerary), SPEC-17 (claims),
> SPEC-20 (city onboarding), SPEC-24/27 (identity and lifecycle), SPEC-41
> (feasibility), or SPEC-43 (security and privacy). It fixes the seams and
> sequencing those capabilities share.
>
> No migration number is claimed. Numbers are assigned at implementation time.

## Goal

Make the backend capable of adding cities, devices, recommendation policies,
model providers, derived features, and data regions without rewriting the
product's integrity, trust, privacy, or scheduling foundations.

"Future ready" means stable and versioned contracts with reversible
migrations. It does not mean deploying speculative infrastructure before load
or team boundaries justify it.

The target remains a modular FastAPI application backed by PostgreSQL and
pgvector. The work is transactional integrity, explicit data authority,
observable decisions, governed AI boundaries, and a repeatable city pipeline.
Microservices, a separate vector database, a graph database, and a learned
ranker are not prerequisites.

## Verified current facts

1. `SupabaseService.save_trip` writes `state_json`, deletes and reinserts
   `trip_node`, then deletes and reinserts `trip_edge` through separate
   PostgREST calls. A failure can leave the blob and normalized graph different.
2. range create saves the trip and party through separate calls. A failure
   between them can leave an orphan trip.
3. normalized itinerary rows are dual-written, but `get_trip` still reads
   `state_json`. The blob therefore hides failed row writes.
4. trip mutation has no expected-version check. Two devices can read the same
   state and the last write silently wins.
5. in-memory and Supabase persistence are independent duck-typed
   implementations, so an in-memory pass does not prove production transaction
   behavior.
6. deterministic feasibility and ranking exist, but the backend does not
   persist the complete feasible candidate set, exclusion reasons, component
   scores, displayed order, or policy version.
7. outcome signals without exposure context cannot distinguish taste from
   availability, prior rank, sponsorship, or a candidate the user never saw.
8. pgvector already exists. The current hybrid RPC is predominantly dense
   cosine similarity plus geography and sponsored contribution; it is not a
   reason to add another database.
9. vectors record a model name in some paths, but one explicit embedding-space
   contract is not enforced. Provider failure can fall back to synthetic
   vectors, which is unsafe in production retrieval.
10. the Ask path shares the itinerary mutation state machine, is not
    catalog-grounded, and can pass application objects toward a model provider.
11. cache scope, conversation context, explicit preferences, behavioral
    features, and catalog claims are not yet distinct memory planes.
12. adding a city still requires hardcoded Python, Dart, allowlist, loader,
    currency, language, bounds, seed, and JSON changes. The loader defaults
    non-Dubai bounds to Laos.
13. `venue_external_id` and `taxonomy_term` exist, but the loader does not yet
    make them the single identity and vocabulary authorities.
14. CI can pass without exercising live PostgreSQL transaction and policy
    behavior, and repository deployment documentation is not fully converged on
    one hosted release path.

## Non-negotiable architecture

### 1. Keep a modular monolith

The production unit remains one FastAPI application unless measured scaling,
fault isolation, team ownership, or residency requirements establish a real
service boundary.

Inside that application:

- command handlers own mutations;
- query handlers own projections;
- a trip unit of work owns graph, party, and event transactions;
- the recommendation service owns feasibility, ranking, and decision records;
- the Ask service owns retrieval and response treatment, not mutation;
- provider ports own routing, weather, embeddings, and model egress;
- repository interfaces are typed and implemented by in-memory and PostgreSQL
  adapters.

Modules may be separated without introducing a network call. Trip mutation is
specifically not split into services while one atomic database transaction is
required.

### 2. PostgreSQL remains the system of record

PostgreSQL stores transactional product state, explicit itinerary edges,
catalog identity, claims, recommendation decisions, consent-scoped signals,
and recomputable derived features.

pgvector remains the dense-retrieval implementation until measured data volume,
latency, recall, or cost demonstrates that PostgreSQL cannot meet the service
level. No separate vector store is introduced because it is fashionable or
because more cities are planned.

Explicit edges in PostgreSQL preserve a future graph-database option. A graph
database is adopted only after a measured multi-hop query workload proves that
the relational representation is the bottleneck.

### 3. Hard feasibility is never learned

SPEC-41 remains authoritative for:

- destination-local opening hours;
- day boundaries;
- previous-node reachability;
- next locked-anchor reachability;
- region and corridor membership;
- identity and duplicate constraints;
- booking locks and explicit traveler caps.

A model, embedding similarity, sponsored contribution, or behavioral feature
may only reorder the feasible set. It cannot make an infeasible candidate
eligible.

### 4. Authority is explicit

- explicit traveler preferences are user authority;
- curated values and claims retain source and freshness under SPEC-17;
- derived features never overwrite curated values;
- raw observations are not the same as verified facts;
- caches are not sources of truth;
- generated prose is not a catalog fact;
- an LLM never adjudicates competing claims;
- an embedding does not establish venue identity.

## Phase A: transactional trip integrity

This phase is the first implementation slice after the Laos reliability
tranche.

### A1. One trip unit of work

Create and mutation commands must commit or roll back all state that belongs to
one logical operation.

At minimum, range create atomically writes:

- `trip_states` compatibility projection;
- `trip_node`;
- `trip_edge`;
- `trip_party` and `party_member`;
- the accepted command/event record when one is required.

A graph mutation atomically writes the new graph and compatibility projection.
It must not expose a delete-all then partially reinserted graph.

Implementation may use direct PostgreSQL access or a narrowly scoped
`SECURITY DEFINER` RPC. If an RPC is used, it must set a fixed search path,
authorize the caller, accept bounded typed input, expose no general SQL
capability, and be covered by SPEC-43's grants/RLS review.

### A2. Optimistic concurrency

Every mutable trip has a monotonically increasing `version`.

- reads return the version;
- mutation commands carry `expected_version`;
- the transaction updates only when the stored version matches;
- mismatch returns a typed `trip_version_conflict`;
- the client refreshes before offering a retry;
- no path silently converts a conflict into last-write-wins.

Offline work uses the same contract. A queued operation created against an old
version is not replayed over newer state without an explicit reconciliation
policy.

### A3. Idempotent commands

Every externally retryable mutation carries a durable `command_id`.

- the same identity, command type, and command ID produce one effect;
- a retry returns the first recorded outcome;
- a command ID cannot be reused with a different payload;
- records retain only the bounded fields needed for idempotency and audit;
- retention follows SPEC-43.

HTTP requests, mobile outbox retries, webhook retries, and background jobs use
the same principle.

SPEC-02 may add a separate offline mutation-command outbox only after this
phase is implemented and the corresponding online command exists. The client
queues the original `command_id`, `expected_version`, and bounded typed payload;
it does not reuse the signal outbox, store raw NLQ, or replay an old command
over newer state. A version or feasibility conflict requires explicit
reconciliation. This spec supplies the server prerequisite, not authorization
for optimistic local re-planning.

### A4. Normalize reads safely

SPEC-16 read cutover proceeds only after transactional writes:

1. compose the normalized rows in shadow mode;
2. compare their public `TripState` projection with `state_json`;
3. measure and investigate every mismatch;
4. make normalized rows authoritative while continuing the v1 wire shape;
5. retain a rollback window;
6. retire `state_json` only after hosted and device evidence.

The Flutter API shape and offline cache format do not change merely because
server storage becomes normalized.

### A5. Identity and schema alignment

Before a large trip or signal history:

- widen new `node_id` values from the current 32-bit truncated identifier to a
  full UUID or ULID-compatible value;
- preserve existing IDs and foreign-key references during migration;
- align authoritative identity and trip key types;
- add missing foreign keys where lifecycle and ownership require them;
- make a schema-walking test fail when a new identity-bearing table is absent
  from merge, export, deletion, and retention handling.

SPEC-24, SPEC-27, and SPEC-43 retain the lifecycle semantics.

### A6. Persistence contract

Define typed interfaces for repositories and the unit of work. In-memory and
PostgreSQL implementations must have the same method shape and error contract.

Tests are split deliberately:

- pure domain tests use in-memory fakes;
- repository contract tests run against both adapters;
- transaction, isolation, constraint, RPC, and RLS tests run against a real
  ephemeral PostgreSQL/Supabase-compatible schema;
- hosted sentinels remain a separate observed gate.

An in-memory atomicity assertion may supplement but never replace the database
transaction proof.

## Phase B: recommendation learning runway

This phase defines the data required before a learned ranker. Collection from
non-owner users remains gated by SPEC-43 consent, ownership, retention,
deletion, and poisoning controls.

### B1. Version the deterministic policy

Every ranked response records a stable `policy_version`. Component definitions,
normalization, tie-breaking, taxonomy revision, catalog revision, and sponsored
formula are versioned.

A policy change does not rewrite historical decisions.

### B2. Record the decision, not only the outcome

A privacy-scoped `recommendation_decision` records:

    decision_id
    subject_pseudonym
    trip_id NULL
    geo_region
    local_slot
    request_context_version
    catalog_revision
    taxonomy_revision
    policy_version
    feasible_candidate_ids
    excluded_candidates[{candidate_id, reason_code}]
    component_scores[{candidate_id, component_key, value}]
    displayed_candidate_ids
    selected_candidate_id NULL
    sponsored_contribution_by_candidate
    created_at

Restricted booking data, raw free text, exact coordinates when coarse region
is sufficient, and unrestricted party data are forbidden.

The schema may normalize arrays into child rows when query volume justifies it.
The logical contract above does not depend on storage shape.

### B3. Link outcomes without rewriting decisions

Accepted swaps, rejected swaps, skips, visits, arrival deltas, and observed
dwell link to a decision when one caused the exposure. Outcomes remain
append-only observations. Derived corrections are recomputed from authorized
inputs and carry:

    subject_type, subject_id, feature_key, value,
    computed_at, method_version, sample_size, confidence

Derived values do not influence feasibility and do not replace curated or
field-verified facts.

### B4. No learned influence by default

The learned weight starts at zero. A model is eligible for bounded influence
only when:

- the candidate exposure record is complete;
- labels span multiple travelers, contexts, and cities rather than one owner;
- train/evaluation splits prevent one traveler or trip leaking across both;
- the model beats the frozen deterministic baseline on held-out ranking and
  itinerary-quality measures;
- city, party, sparse-data, sponsorship, and cold-start slices are reported;
- privacy, consent, deletion, poisoning, and rollback gates pass;
- the model cannot admit an infeasible candidate;
- a kill switch restores the prior deterministic policy without a client
  release.

No fixed event count in this spec substitutes for a power and coverage review.
Dozens of events or one traveler are not sufficient evidence for a population
ranker.

The first candidate model should be interpretable, such as regularized linear
ranking or a constrained tree model over explicit features. Collaborative
filtering, user embeddings, sequence models, and neural ranking remain
deferred until item overlap and user volume justify them.

## Phase C: retrieval and embedding integrity

### C1. Structured and lexical retrieval first

Venue search applies exact region, category, audience, geography, and
eligibility filters before an expensive candidate limit. Name and localized
name retrieval gains a lexical channel suitable for exact names,
transliterations, and misspellings.

Dense retrieval is one recall channel, not the identity authority and not the
whole ranker. Lexical and dense results may be fused only through a versioned,
tested policy.

### C2. Explicit embedding spaces

Every vector belongs to an immutable `embedding_space_id` that fixes:

- provider and model;
- model revision where available;
- vector dimension;
- input construction and normalization version;
- entity or passage type;
- created time.

A query searches exactly one compatible space. Mixed-space similarity is a
typed configuration error, not a low score.

Production provider failure does not write synthetic vectors into a real
space. Retrieval either uses a declared lexical fallback or fails with a named
treatment.

### C3. Re-embedding is resumable

A model migration:

1. creates a new embedding space;
2. writes new vectors beside old vectors;
3. records bounded job progress;
4. verifies coverage and retrieval goldens;
5. switches the active query space through configuration;
6. retains rollback until acceptance;
7. removes old vectors under an explicit retention decision.

Venue identity embeddings and licensed Ask passage embeddings are separate
entity types even if they use the same provider model.

### C4. Indexes follow measurements

At the current catalog size, exact pgvector scan may be cheaper and more
accurate than approximate search. IVFFlat/HNSW parameters are selected from
measured per-region row counts, p95 latency, recall, and write cost.

A separate vector database is considered only after measured volume or service
levels cannot be met by PostgreSQL, not simply because the route adds cities.

## Phase D: AI and memory boundaries

SPEC-25 owns the Ask behavior and SPEC-43 owns allowed egress. This spec fixes
the architecture those capabilities use.

### D1. Ask is a separate query service

Informational Ask does not run through the structural mutation pipeline after
intent classification. Its flow is:

    question
    -> deterministic intent and authorization
    -> retrieve trip, catalog, and resolved claim facts
    -> construct sourced claims
    -> policy and budget decision
    -> deterministic template or approved light-model phrasing
    -> typed response treatment and claim envelopes

Retrieval miss, absent key, budget refusal, breaker, and model failure are
distinct treatments. A model call is not attempted when the deterministic
preconditions fail.

Natural-language input, including conversational query, classifies into a
closed typed command before any retrieve or mutate step:

- `ASK_FACT` retrieves grounded trip and catalog facts and returns a sourced
  answer; it never writes itinerary rows;
- `SWAP_NODE`, `ADD_BOOKING`, and other existing trip-event types become
  structured patches on the current mutation path;
- `OUT_OF_SCOPE` refuses with a reason.

Classification may use a light model. Retrieval and feasibility remain
deterministic. There is no free-form tool loop, supervisor graph, or
multi-agent runtime on this path. Informational Ask and itinerary mutation
do not share an execution graph after the command is typed.

### D2. Four memory planes

1. **Conversation context.** A bounded number of turns for one authorized Ask
   session, short-lived and identity/trip scoped.
2. **Explicit preferences.** Editable traveler choices and hard caps. The
   traveler is authority.
3. **Behavioral features.** Recomputable, consent-scoped aggregates with
   method version, sample size, confidence, recency, and deletion behavior.
4. **Catalog claims.** Sourced, append-only public facts resolved under SPEC-17.

There is no generic "agent memory" blob that summarizes a traveler. Model
inference cannot silently become an explicit preference. Long-term chat
transcripts are not embedded as traveler memory by default.

### D3. One AI gateway

Every completion and embedding call uses one deny-by-default gateway with:

- intent-specific outbound DTOs;
- approved provider, endpoint, model, region, retention, and fallback policy;
- prompt and model-policy version;
- pre-call redaction and canary tests;
- cost, token, timeout, concurrency, and daily spend bounds;
- named response treatment;
- telemetry that omits raw questions and restricted content.

No feature passes a `TripState`, `TripNode`, booking object, or arbitrary
application dictionary directly to a provider.

### D4. Cache by data class

- public, source-versioned catalog facts and deterministic templates may use a
  shared cache;
- private generated responses are not cached by default;
- an approved private cache includes identity and complete
  trip/source/prompt/model context in the key;
- restricted fields and raw personal free text make an entry ineligible;
- expiry means physical purge, not merely read-time rejection.

### D5. Mutations require human confirmation

A model may propose a structured itinerary patch. It cannot persist that
patch. Persistence uses only the existing trip-event path and the Flutter
confirmation surface (swap sheet, booking edit, or equivalent HITL card).
Search and apply remain the SPEC-41 feasibility predicates. Reject any
design in which an LLM, agent, or background worker writes trip, party, or
booking rows.

### D6. Proactive recommendations stay on the alert path

Weather, closure, crowd, delay, and departure signals follow SPEC-29 and
SPEC-35: ingest evidence, evaluate impact on the active trip, emit a
candidate list, then render in-app or later SPEC-27 push. That path does
not mutate the itinerary, consume reroute quota, or call an LLM. Do not
introduce a second agent graph, durable workflow engine, or general event
bus to host proactive recommendations.

### D7. Provider ports, not MCP as runtime

Maps, weather, flights, places, and the constraint solver are application
ports behind FastAPI. MCP is reserved for later traveler-side connectors
such as mail or calendar ingest under SPEC-10 and SPEC-43. It is not how
the Ask path, swap path, or solver is invoked.

## Phase E: city platform contract

SPEC-13, SPEC-17, and SPEC-20 own implementation. Before Bangkok data is loaded
as the second real onboarding case, they must jointly provide:

- a database-backed country/region registry and cached client projection;
- region-specific bounding boxes, IANA timezone, ordered languages, script,
  currency and exponent, payment/fare context, and transport modes;
- no Dubai or Laos default on an unknown write path;
- `venue_external_id` as the source-first upsert and deduplication key;
- one taxonomy authority enforced by loader and database;
- one city-pack schema and one loader path for hosted and in-memory data;
- unknown hours represented as unknown, never invented defaults;
- overnight hours represented consistently with SPEC-41;
- subjective attributes stored as sourced claims, not unsourced venue columns;
- a licence and attribution record for every source;
- a refusal report that blocks advertisement on any failed gate;
- catalog and pack-schema revisions carried into caches, search, decisions, and
  goldens.

Bangkok proves the factory. It is not added through a temporary Python/Dart
exception. No Thailand, Vietnam, Cambodia, or Philippines pack is ingested
before the machinery can refuse an invalid city.

## Phase F: jobs, operations, and release truth

### F1. Add the smallest durable job substrate when needed

The first real retention, cache purge, re-embedding, catalog validation, or
derived-feature batch introduces:

- an idempotent Cloud Run job or equivalent bounded worker;
- Cloud Scheduler or an explicit operator trigger;
- a `job_run` ledger with job type, input/version key, status, attempts,
  timestamps, result counts, and redacted error code;
- retry and dead-letter/operator behavior;
- metrics and alerting.

Kafka, Celery, Redis queues, and a permanent worker fleet remain out of scope
until measured throughput or latency requires them.

### F2. One release target

Documentation and automation converge on the observed Cloud Run deployment
path. A legacy provider name is not retained as a second implied production
target.

### F3. CI proves production-shaped behavior

Before the first non-owner release:

- one supported Python version and resolved dependency set are authoritative;
- migrations run from zero in CI against ephemeral PostgreSQL;
- transaction rollback, concurrency, constraints, and RLS run against that
  database;
- documentation hygiene and schema/source drift guards remain;
- actions are pinned to immutable revisions;
- secret, dependency, static, container, and SBOM checks satisfy SPEC-43;
- hosted and device observations remain separately recorded, not inferred from
  CI.

## Delivery sequence

1. With SPEC-41 A3b complete at `7f25042`, finish SPEC-10 provider-aware
   paste, SPEC-25 grounded trip-scoped Ask, and the Laos hosted/API/APK
   re-verification.
2. Implement Phase A transactional integrity, concurrency, idempotency, and
   persistence contracts.
3. Implement SPEC-43, including SPEC-24/27 dependencies, before any non-owner
   distribution or personal-data LLM use.
4. Implement SPEC-13 plus the minimum SPEC-17 claim store and SPEC-20 city
   factory requirements in Phase E.
5. Onboard Bangkok through the factory and record actual effort and refusals.
6. Enable Phase B decision collection only for consented subjects after
   SPEC-43. Learned influence remains zero.
7. Add derived corrections and offline evaluation; introduce bounded learned
   influence only after the B4 evidence gate.
8. Add further cities through the same pack and refusal path.

Phases C, D, and F are taken in bounded slices with the capability that needs
them. They are not a reason to pause the active product path for speculative
platform work.

## Acceptance

### Integrity

- [ ] create with party commits completely or leaves no trip, party, node, edge,
      or command residue after an injected failure
- [ ] graph mutation commits the old or new graph, never a partial replacement
- [ ] two concurrent writes from the same version produce one success and one
      typed conflict
- [ ] replaying one command ID produces one effect and the same outcome
- [ ] normalized shadow reads equal the public blob projection before cutover
- [ ] existing node IDs survive widening and all edge references remain valid
- [ ] repository contracts run against both adapters; transaction proofs run
      against PostgreSQL

### Recommendation and retrieval

- [ ] every recommendation carries policy, catalog, taxonomy, and context
      versions
- [ ] the complete feasible exposure and exact exclusion reasons are recorded
      without restricted data
- [ ] score components and sponsored contribution are inspectable
- [ ] outcomes link to decisions without rewriting them
- [ ] learned influence defaults to zero and cannot weaken feasibility
- [ ] held-out evaluation, slice reports, rollback, and kill switch pass before
      a learned policy receives traffic
- [ ] queries cannot compare vectors from different embedding spaces
- [ ] provider failure cannot write synthetic production vectors
- [ ] a re-embedding job can resume, switch, and roll back
- [ ] lexical and dense retrieval goldens pass for names and localized names

### AI and city platform

- [ ] Ask authorization and retrieval precede every optional model call
- [ ] natural-language input classifies to a typed command with no free-form
      tool loop
- [ ] mutation proposals persist only through existing trip events and HITL
- [ ] proactive candidates stay on SPEC-29/35 evaluators
- [ ] maps, weather, flights, and the solver remain application ports; MCP is
      later ingest only
- [ ] conversation, preference, behavioral, and catalog memory planes have
      distinct authority, scope, retention, and deletion rules
- [ ] no application object crosses the AI gateway
- [ ] private cache entries cannot cross identity or context versions
- [ ] region, taxonomy, external identity, claims, pack, licence, and refusal
      gates exist before Bangkok is advertised
- [ ] Bangkok onboards end to end without a city-specific code exception
- [ ] an invalid city fails before any partial database write or advertisement

### Operations

- [ ] the first batch job is durable, idempotent, resumable, observable, and
      redacted
- [ ] CI rebuilds and tests the database from zero with transaction and RLS
      proofs
- [ ] release documentation and automation name one observed hosted target
- [ ] suite results report pass and skip reasons under R8; hosted and device
      gates are observed by the party able to run them

## Explicitly deferred

- microservices;
- event sourcing;
- Kafka or a general event bus;
- a separate vector database;
- a graph database;
- Redis/Celery without a demonstrated queue workload;
- collaborative filtering before meaningful cross-user item overlap;
- user embeddings and similar-user retrieval before SPEC-43 and adequate data;
- neural or sequence ranking before an interpretable baseline;
- autonomous tool-calling agents;
- LangGraph, AutoGen, or other multi-agent orchestration runtimes;
- Temporal or equivalent durable agent workflows;
- Redis Streams, NATS, or a general bus as the proactive alert fabric;
- OR-Tools or another external CSP engine until `pack_day` constraint
  volume requires it;
- MCP as the in-process tool runtime for maps, weather, flights, or the
  solver;
- Mem0 or other generic long-term agent-memory products;
- generic long-term conversation memory;
- model-generated scheduling or eligibility;
- active-active multi-region deployment before a legal or service requirement;
- adding a city through another hardcoded exception.
