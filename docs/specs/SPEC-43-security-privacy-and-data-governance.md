# SPEC-43: Security, Privacy and Data Governance Foundation

> Status: SPECIFIED. Not implemented.
>
> Sequence: start after the Laos reliability and build tranche is complete:
> SPEC-41 scheduling, SPEC-10 provider-aware paste, SPEC-25 grounded
> trip-scoped Ask, and the resulting hosted API / signed APK verification.
> Finish this spec before any build is distributed to a person other than the
> owner, before production LLM processing of personal trip data, and before the
> planned December 2026 public launch.
>
> This is an engineering and product contract, not legal advice. Market launch
> still requires counsel to confirm the operating entity, controller roles,
> jurisdiction triggers, processor contracts, and current local rules.
>
> SPEC-44 owns the shared transaction, optimistic-concurrency, idempotent-command,
> persistence-contract, recommendation-telemetry, embedding-space, and
> AI-memory architecture. Its Phase A runs after the Laos tranche and before
> this release foundation. This spec remains authoritative for identity,
> consent, ownership, retention, deletion, egress, and public-release gates.

## Goal

Make Travel Buddy safe to operate beyond its current one-owner test phase.

The product now holds data that can expose where a traveller will be, when they
will be away, who they may be travelling with, and how to access or modify a
reservation. A random user or device identifier does not make that data
anonymous. Exact itinerary sequences, booking references, free-text notes,
party age bands, behavior, and questions are personal data even when no name or
email is present.

This spec provides one owner for twelve identified gaps. It does not replace
the capabilities that already own identity, offline behavior, signals,
observability, Ask, or data rights. It adds system-wide invariants and amends
those specs where a local decision is insufficient.

## Current owner-only risk acceptance

Until this spec is implemented:

1. The owner is the only tester and user.
2. No APK is distributed to another person.
3. The hosted LLM key is not enabled for personal trip traffic. Deterministic
   and named fallback behavior remains acceptable for the owner test.
4. No claim is made that data remains in India, the UAE, Laos, the EU, or any
   other jurisdiction merely because the primary database is in Mumbai.
5. No learned personalization, advertising audience, data sale, or third-party
   behavioral sharing is enabled.
6. The exception expires at the first non-owner tester or the public-launch
   gate, whichever comes first. It is not a permanent "MVP" exemption.

## Non-negotiable architecture

### Data classes

| Class | Examples | Default treatment |
|---|---|---|
| Restricted | booking references, booking notes, receipt tokens, auth tokens | never log or send to an LLM; mask in UI; encrypt locally and server-side when server storage is necessary |
| Sensitive by context | exact trip dates, ordered venue coordinates, party age bands, visit and arrival history | owner-scoped; purpose-limited; short retention; never sold or used for ads |
| Pseudonymous personal | device UUID, account subject, signal identifiers, embeddings linked to a person | protected as personal data; rotation, deletion, export, and access controls apply |
| Public catalog | sourced venue facts, public coordinates, source URLs | globally cacheable only without traveller context; provenance and licence remain attached |
| Operational | request IDs, IP/platform logs, errors, cost and latency | structured, redacted, access-audited, region and retention controlled |

### Separation of planes

1. **Private itinerary vault.** Identity-scoped, region-bound storage for
   trips, booking anchors, and exact schedule. It is not the analytics
   warehouse.
2. **Behavioral learning plane.** Purpose-scoped pseudonyms, closed signal
   schemas, no booking secrets, no unrestricted free text, and no exact
   location when a coarse fact is sufficient.
3. **Public catalog plane.** Venue facts, sources, freshness, licence, and
   sponsorship provenance. Only this plane may be shared in a global cache by
   default.
4. **AI egress gateway.** One allowlisted serializer controls every completion
   and embedding request. No feature calls a model provider directly with an
   application object.

### Child and family position

Travel Buddy accounts are for adults aged 18 or older for the initial launch.
A parent or guardian may describe a party using coarse age bands. The product:

- does not request a child's name, date of birth, email, device identity, or
  separate account;
- does not build a child-level behavioral profile;
- does not target advertising or marketing using child or family signals;
- does not infer a child's health, religion, diet, or accessibility needs;
- reviews this position before marketing the app as child-directed or allowing
  independent use by minors.

## The twelve gaps and proposed solutions

### Gap 1: self-issued anonymous UUID acts as an account credential

**Current fact.** The client creates a UUID and sends
`Authorization: Anonymous <uuid>`. The UUID is high entropy and stored in
secure storage, but the server did not issue it, cannot expire it, and cannot
distinguish a legitimate device from an attacker who selected another UUID.
Unlimited new UUIDs also bypass per-user cost quotas.

**Solution.**

- Use Supabase anonymous sign-in to issue a short-lived JWT without requiring
  email or other profile PII.
- Verify tokens from the project JWKS, including signature algorithm, `kid`,
  issuer, audience, expiry, subject, role, and anonymous claim.
- Support key rotation and reject a valid token from another Supabase project.
- Keep a device UUID only as a non-secret local diagnostic identifier.
- Apply rate and cost limits to account, device reputation, and IP rather than
  trusting one identifier.
- Preserve SPEC-24's later anonymous-to-Google/Apple account link and
  transactional history merge.

**Acceptance.**

- A client-selected UUID alone cannot read or mutate a trip.
- Replaying an expired or revoked token fails.
- A token from another project fails.
- Rotating signing keys does not require shipping an APK.
- Creating many anonymous accounts cannot reset all cost and abuse limits.

### Gap 2: personal tables are not comprehensively protected by RLS

**Current fact.** Migration 0007 enables RLS on seven tables, but not on core
personal tables including `user_tiers`, `trip_states`, `event_log`,
`cached_responses`, `trip_node`, and `trip_edge`. The party insert policies use
`WITH CHECK (true)`. The backend service-role key bypasses RLS.

**Solution.**

- Enumerate every public table, view, function, and grant from the live schema.
- Revoke `anon` and `authenticated` access by default, then grant the minimum
  required surface.
- Enable and force RLS on every personal table exposed through PostgREST.
- Base trip, party, node, edge, event, and signal policies on authoritative
  trip ownership, never on the existence of a signal.
- Remove permissive authenticated inserts.
- Isolate service-role operations. Prefer caller-scoped JWT access or narrow
  security-definer RPCs with explicit ownership checks for user operations.
- Keep the service role for bounded administrative jobs only and store it in
  a managed secret service.

**Acceptance.**

- A fresh-schema test fails if any personal table lacks RLS or has an unsafe
  public grant.
- Two real JWTs cannot read, insert, update, or delete each other's records
  through PostgREST.
- Service methods cannot bypass ownership by changing an object ID.
- Hosted policy sentinels are observed before the migration is marked applied.

### Gap 3: personal itinerary data can cross the LLM boundary

**Current fact.** The heavy response path serializes itinerary nodes. A node
may contain a booking reference, notes, exact time, and coordinates. Search or
Ask text may be sent for embeddings. The configured heavy fallback chain can
move a request among model providers.

**Solution.**

- Create and swap remain deterministic. An LLM may phrase an already-approved
  result but does not need the full trip to do so.
- Add one outbound AI DTO for each approved intent. Deny every field not
  explicitly named.
- Never send user ID, auth data, booking reference, notes, receipt, raw pasted
  text, exact coordinates, unrelated itinerary days, or unrestricted party
  data.
- Run secret/PII redaction after serialization and before transport, with
  canary tests.
- Approve each model, endpoint, provider, data region, retention mode, training
  setting, human-review setting, and subprocessor contract. Disable automatic
  fallback to an unapproved provider or region.
- Prefer deterministic retrieval templates. Use a light model only when it
  adds value after retrieval.
- Label AI interaction and distinguish generated phrasing from sourced facts.

**Acceptance.**

- Canary booking codes, notes, IDs, receipts, and coordinates never appear in
  completion, embedding, trace, fallback-provider, or model-error payloads.
- Provider failure cannot route data to an unapproved provider.
- Retrieval miss and key absence invoke no model.
- AI telemetry records model, cost, source IDs, region, and fallback state
  without recording the question or restricted content.

### Gap 4: data rights and retention are not implemented

**Current fact.** SPEC-27 specifies export and deletion, but there is no
endpoint or client flow. Trips, signals, events, parties, and several local
caches have no enforced retention lifecycle. A cache expiry predicate does not
delete an expired row.

**Solution.**

- Implement self-service human-readable export, correction where applicable,
  account deletion, and local-data clearing.
- Use the shared SPEC-24/27 schema walk so a new identity-bearing table fails a
  test until merge, export, and deletion handle it.
- Delete raw signals and person-linked features. Population aggregates may
  survive only when they cannot single out or reconstruct a contributor.
- Maintain deletion tombstones so a backup restore cannot resurrect a deleted
  account. State the vendor backup expiry window honestly.
- Run retention jobs and record completion metrics without retaining the
  deleted content.

**Proposed product defaults, subject to counsel.**

| Data | Proposed default |
|---|---|
| raw pasted confirmation text | memory only; never written |
| booking reference and private notes | local-first; if synced, delete 30 days after the booking or trip ends |
| identifiable behavioral signals | 12 months, then delete or irreversibly aggregate |
| private semantic response cache | at most 24 hours and actively purged |
| application error data | 30 days unless an active incident requires a documented hold |
| failed mobile outbox rows | 30 days, then purge with a visible failed-sync count |
| trip history | user-controlled; proposed 24-month inactive default with advance notice |
| backups | provider window plus deletion tombstone and tested restore procedure |

Where CERT-In directions apply, required security logs are retained securely in
India for the applicable period and are separated from product analytics.

**Acceptance.**

- Export covers identity, trips, bookings, parties, preferences, signals,
  events, provenance, consent, and processors in a readable format.
- Deletion leaves zero identity references across live tables and local stores.
- A synthetic new identity table makes the schema-walking test fail.
- A restore drill does not make a deleted account active again.
- Expired cache and outbox rows are physically removed.

### Gap 5: the offline trip vault is plaintext and backup behavior is implicit

**Current fact.** Full trip JSON, booking fields, signals, alerts, outcomes,
and notification data are stored in ordinary SQLite. Only the UUID uses secure
storage. Android backup exclusions are not declared.

**Solution.**

- Encrypt the database or restricted columns with a key protected by Android
  Keystore and, when iOS exists, Keychain using an appropriate accessibility
  class.
- Do not store the raw pasted confirmation.
- Prefer keeping booking references local. If they must sync, apply
  envelope/field encryption with managed keys server-side as well.
- Exclude the database, secure tokens, and restricted files from Android/iOS
  backup and transfer mechanisms.
- Mask booking references and private notes until explicit reveal.
- Obscure restricted screens in the task switcher; make screenshot policy a
  deliberate product decision rather than a framework default.

**Acceptance.**

- Plaintext canaries are absent from the database file and extracted backup.
- Losing the device keystore key does not silently fall back to plaintext.
- Raw paste text never reaches disk.
- Booking references are masked by default and absent from screenshots used by
  diagnostics.

### Gap 6: sign-out does not revoke or clear the prior identity

**Current fact.** The profile action only navigates to onboarding. It does not
revoke or clear a Supabase session, stop synchronization, rotate identity, or
wipe account-scoped local records.

**Solution.**

- Treat sign-out as a lifecycle operation, not navigation.
- Stop and drain or explicitly discard identity-scoped sync work.
- Revoke/clear the provider session and tokens.
- Delete every prior identity's trip, place, home, alert, notification, loved,
  outcome, app-state, and outbox row from the device.
- Create a new anonymous identity only after the prior account is inaccessible.
- Require reauthentication for destructive account deletion and sensitive
  account changes.

**Acceptance.**

- After sign-out, the prior API session fails and no prior local trip renders.
- Account A to account B switching exposes no row from A.
- Router redirects cannot bounce a signed-out user back into the old session.
- Sync cannot upload an old identity's outbox under a new identity.

### Gap 7: behavioral capture has a consent stub, not a policy

**Current fact.** `require_consent()` always passes. Signals can describe
visits, skips, loves, dishes, timestamps, and stamped party age bands.

**Solution.**

- Separate necessary trip operation, optional product analytics, optional
  personalization, optional location features, and marketing into named
  purposes.
- Record scope, lawful basis, notice version, locale, grant/withdrawal time,
  source, and expiry where relevant.
- Do not enqueue an optional signal before the required choice.
- Withdrawal blocks new capture immediately and deletes unsent rows. It also
  excludes or deletes person-linked training inputs and features.
- Do not stamp age bands into every signal. Join authorized party context at
  analysis time or use a coarse, purpose-approved aggregate.
- Core itinerary use remains available when optional analytics or
  personalization is declined.

**Acceptance.**

- Declining optional analytics creates no signal and no outbox row.
- Withdrawal works offline immediately and syncs the rights request later.
- Consent to analytics does not imply consent to personalization or marketing.
- Historical training input honors withdrawal/deletion.
- No child-level signal or profile can be created.

### Gap 8: semantic cache can cross user boundaries

**Current fact.** The process-wide cache is scoped by semantic similarity,
region, and current venue, not by identity, trip, date, source version, or a
complete grounded context. The persistent cache schema is even more general.

**Solution.**

- Globally cache only public catalog facts and deterministic templates that
  contain no traveller context.
- Do not cache user-specific generated prose by default.
- If a private response is worth caching, scope it to the owning identity and
  a complete context/source/version hash.
- Store an HMAC or normalized intent key instead of raw question text where
  possible.
- Never cache a response containing restricted fields, free-form personal
  details, or another person's data.
- Actively purge expiry rather than relying only on read-time filtering.

**Acceptance.**

- Similar questions from two users cannot share a private response.
- A change in trip, date, source version, or relevant venue facts causes a
  miss.
- Restricted-content canaries make the cache refuse storage.
- Expired rows are deleted from memory and persistent storage.

### Gap 9: signal ingestion lacks trip ownership and poisoning controls

**Current fact.** The server derives `user_id`, but a supplied `trip_id` is
used to read trip and party context without first requiring ownership. Client
`value_json` is flexible, and derived writers can act on linked trip data.

**Solution.**

- Require trip ownership before accepting any trip-linked signal or deriving
  party, arrival, duration, or edge data.
- Validate ownership again inside the transaction that writes a derived fact.
- Define a closed schema, value range, and size limit for every signal type.
- Separate client observation from server-verified or corroborated evidence.
- Add contributor quality, anomaly, rate, location/time plausibility, and
  minimum-sample gates before a signal influences recommendations.
- Quarantine suspicious data without using it for ranking.

**Acceptance.**

- User B submitting user A's trip ID is rejected and changes no signal, party
  context, arrival fact, edge, or feature.
- Unknown fields, excessive values, oversized JSON, and impossible timestamps
  are rejected with typed errors.
- One user or device cannot materially move a venue score.
- Derived facts retain method version, sample size, and provenance.

### Gap 10: errors and provider failures can carry sensitive values

**Current fact.** Validation details, exception text, and full tracebacks can
enter logs or the in-memory ring. Debug mode exposes the ring without separate
administrator authentication. Some provider error strings are returned to the
client, and provider keys may appear in request URLs.

**Solution.**

- Use one structured logging API with field allowlists and centralized
  secret/PII redaction.
- Do not log request bodies, raw questions, booking references, notes, tokens,
  receipts, provider URLs containing keys, or model prompts/responses.
- Return stable public error codes and request IDs, never provider text.
- Make a production startup assertion reject debug mode.
- Put diagnostics behind administrator IAM even outside production.
- Regionalize log buckets, restrict access, record access, and enforce
  retention.

**Acceptance.**

- Log-canary tests cover validation, webhooks, model failures, Maps/weather
  failures, database errors, and booking mutations.
- Debug diagnostics are unreachable without administrator authorization.
- Production refuses to start with debug enabled.
- User-facing errors contain no upstream body, URL, key, or traceback.

### Gap 11: there is no general abuse or resource-consumption boundary

**Current fact.** Reroutes have a quota, but the API has no visible general
per-route rate limit, request-body limit, anonymous-account creation control,
or LLM budget that survives UUID rotation.

**Solution.**

- Put the public Cloud Run service behind an approved gateway/load-balancer
  boundary with per-IP, per-account, per-device-reputation, and per-route
  limits.
- Bound HTTP body size, collection counts, every free-text field, JSON depth,
  search radius, top-k, model tokens, concurrency, and provider timeout.
- Maintain daily and rolling provider-spend circuit breakers.
- Rate-limit webhooks while preserving provider retries and idempotency.
- Use Play Integrity/App Attest only as an abuse signal, not as a hidden
  advertising identity or an absolute availability dependency.
- Alert on identity farms, signal floods, cache growth, authorization failures,
  and abnormal provider spend.

**Acceptance.**

- UUID/account rotation does not bypass all limits.
- Oversized and deeply nested payloads fail before expensive parsing or model
  calls.
- Load tests cannot exceed the configured downstream spend budget.
- Valid offline signal batches and webhook retries remain reliable.

### Gap 12: release transport and mobile cache isolation are incomplete

**Current fact.** The API base URL defaults to HTTP and release code does not
reject cleartext configuration. `cache_trip` is keyed only by trip ID and
`cache_place` by place reference. Offline itinerary fallback does not verify
the cached user. Chat text is placed in a route query string.

**Solution.**

- Make release builds fail unless all API and Supabase endpoints are HTTPS.
- Declare Android network security and iOS ATS policy explicitly. Do not use a
  permissive release exception for the emulator development URL.
- Key every private cache row by identity and verify cached ownership before
  rendering.
- Move chat text and other private state out of route URLs and deep links.
- Authorize every incoming deep link against the current identity before
  opening a trip.
- Add privacy-safe lock-screen defaults before OS push is implemented.

**Acceptance.**

- A release build with any HTTP endpoint fails in CI and at startup.
- Switching identity cannot read a stale trip or place row.
- Route logs and restored navigation contain no question text.
- A deep link for another user's trip is refused.
- Core itinerary use still works when optional location permission is denied.

## Data sovereignty and transfer contract

The current Cloud Run and Supabase primary region is Mumbai. This is useful for
the initial India posture but is not, by itself, proof of data residency.

Before a residency or sovereignty statement is published:

1. Add immutable `data_region` routing metadata to the identity or tenant.
2. Inventory primary storage, replicas, backups, logs, support access,
   analytics, model inference, model retention, subprocessors, and disaster
   recovery.
3. Record controller/processor role, purpose, data classes, destination,
   transfer mechanism, retention, deletion behavior, and incident deadline for
   every recipient.
4. Execute processor DPAs and, where required, SCCs, UK transfer terms, transfer
   assessments, UAE safeguards, or Lao owner consent and recipient safeguards.
5. Do not create regional stacks until a launch market or contract justifies
   the operational cost. Build the routing seam now so regional separation does
   not require rewriting identifiers later.
6. Do not claim local processing when only storage at rest is local.

## Compliance map for launch review

### India

The DPDP Act and Rules are staged. As recorded in September 2026, institutional
provisions are in force, a further tranche begins 14 November 2026, and most
operational Act and Rule duties begin 14 May 2027. Build now for standalone
notice, valid consent or permitted use, security safeguards, grievance and
rights handling, erasure, breach notice, and the under-18 child rules.

Separately determine whether CERT-In directions apply to the operating entity
and service. The incident process must be capable of the applicable six-hour
report and India log-retention requirement without treating security logs as
product analytics.

### EU / EEA and United Kingdom

If Travel Buddy intentionally offers service to or monitors people in these
markets, GDPR or UK GDPR can apply without a local company. Exact itinerary and
behavioral profiling require a documented lawful basis, processor terms,
rights workflow, transfer mechanism, and likely a DPIA before scaling.
Authority breach notice may be due within 72 hours. Since 2 August 2026, an EU
user must be informed when interacting with an AI system unless it is obvious.
The UK also requires a usable privacy complaint process and child-sensitive
design where children are likely users.

### UAE

The federal PDPL is active and governs security, rights, processors, and
cross-border safeguards within its scope. DIFC and ADGM have separate regimes.
The 2025 federal Child Digital Safety law is also active. UAE counsel must
confirm the entity/free-zone position, current executive rules, breach process,
and any sector-specific localization before launch there.

### Laos

The 2017 Law on Electronic Data Protection is the principal verified official
source, and its official English text is unavailable. Treat consent, secure
handling, accuracy, deletion/retention, and protected cross-border transfer as
design requirements. Obtain local advice before claiming compliance. The
reported 2026 cybersecurity changes remain unverified until authoritative text
and applicability are reviewed.

### California and the wider United States

CCPA is threshold-dependent, but FTC unfair/deceptive-practice authority,
state breach laws, contractual promises, and reasonable-security duties matter
earlier. Treat precise location as sensitive. If the service is child-directed
or has actual knowledge of an under-13 user, COPPA applies. Do not sell/share
location or behavior, overstate recommendation accuracy, conceal sponsored
ranking, or use dark patterns.

## Security operations and software supply chain

The product controls above are necessary but not sufficient. Before public
launch:

- store secrets in managed secret storage, rotate them, and use least-privilege
  service accounts;
- fail production readiness when database, auth, required migrations, or
  security settings are absent;
- implement SPEC-44's transactional and idempotent command contract for trip,
  node, edge, party, event, signal, and webhook writes where partial state is
  unsafe;
- establish a migration history and live drift check;
- pin CI actions to immutable revisions and dependencies to reviewed
  resolutions;
- add secret scanning, dependency/SCA, SAST, migration/RLS tests, container
  scanning, and an SBOM;
- document vulnerability intake, incident commander, contact tree, provider
  escalation, evidence preservation, regulator clocks, user communication, and
  post-incident review;
- run backup restore, deletion-after-restore, key rotation, and access-review
  drills;
- arrange an independent penetration test before broad public distribution.

SOC 2 or ISO 27001/27701 certification is not the first task. Evidence-producing
controls come first; certification follows when customers, partners, or scale
justify it.

## Delivery phases

### Phase 0: owner-only guard, now

Documentation only: keep distribution owner-only, keep personal trip data out
of production LLM calls, and make no residency or compliance claim.

### Phase 1: identity and authorization

Gaps 1, 2, 6, and 9:

- server-issued anonymous JWT;
- complete RLS and grants;
- real sign-out and identity-scoped wipe;
- trip ownership and signal poisoning controls.

### Phase 2: vault and privacy lifecycle

Gaps 4, 5, 7, and 12:

- export, deletion, retention, and backup tombstones;
- encrypted offline and restricted server fields;
- purpose/consent ledger and withdrawal;
- release HTTPS, cache isolation, and private navigation state.

### Phase 3: AI, observability, and abuse

Gaps 3, 8, 10, and 11:

- AI egress allowlist and approved provider-region matrix;
- safe cache boundaries;
- redacted diagnostics;
- request, identity, model, and spend limits.

### Phase 4: public-launch governance

- privacy and AI notice;
- processor and subprocessor register;
- transfer and residency record;
- rights and grievance operations;
- age-position review;
- incident and breach drills;
- app-store privacy disclosures;
- independent security test and closure of high findings.

Phases may be implemented as separate briefs and PRs. Every phase must preserve
the Laos offline itinerary, driver card, deterministic feasibility, and honest
fallback behavior.

## Public-launch acceptance

- [ ] All twelve gap acceptance sections pass.
- [ ] No P0 or High security/privacy finding remains open.
- [ ] One owner can export and delete all data without support intervention.
- [ ] A two-user hosted test proves object and row isolation.
- [ ] A shared-device test proves sign-out and account switching isolation.
- [ ] An LLM canary test proves restricted fields never leave the gateway.
- [ ] A backup extraction and restore drill proves encryption and deletion.
- [ ] Consent withdrawal stops capture and future personalization.
- [ ] Production readiness refuses debug, HTTP, missing auth, missing database,
      and unapplied security migration states.
- [ ] Incident exercise meets the shortest applicable notification clock.
- [ ] Public notice, processor register, retention schedule, child position,
      AI label, sponsorship disclosure, and app-store declarations match the
      observed product.
- [ ] Counsel records the approved December launch markets and unresolved
      jurisdiction-specific conditions.
- [ ] Backend, Flutter, live Supabase, hosted API, signed APK, and device gates
      are run by the party that can actually observe them.

## Explicitly out of scope

- Building this work before the active Laos reliability/build tranche is done.
- Collecting passport, government ID, biometrics, contacts, background
  location, or a child's direct identity.
- Advertising profiles, data brokerage, or selling/sharing precise location.
- Claiming legal compliance from a checklist or cloud region.
- Pursuing certification before the product controls exist.
