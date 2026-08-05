# SPEC-01 — Migration tooling + first end-to-end signal slice
*Implements roadmap items #8 (versioned migrations) and #1 (signal capture, vertical slice).*
*Goal: prove the full path — versioned schema -> ingest API -> Flutter emitter -> test — for ONE
signal type (`user_loved`). All other signal types (§16) follow this exact pattern afterward.*

## Guiding rules (do not skip)
1. **Vertical slice, not schema-first.** A signal in the DB with no client emitter is worthless.
   This spec is DONE only when a tap in the Flutter app results in a row in Supabase AND a passing
   test. Do not move to other signal types until this round-trips.
2. **Idempotent from day one.** Client generates the event UUID; server upserts on it. This is the
   foundation the offline queue (SPEC-02) depends on — get it right now.
3. **Migrations are the ONLY way schema changes.** After this spec, no hand-run SQL in the Supabase
   console. Every change is a committed, ordered, reversible migration file.
4. **Backend stays backend-agnostic.** Capture must work with the in-memory backend (for tests) AND
   Supabase (for real), behind the existing `db_provider` seam.

---

## PART A — #8: Migration tooling

### A.1 Choose the tool
Use **Supabase CLI migrations** (`supabase/migrations/*.sql`) — it's native to the DB we're on,
versioned, ordered by timestamp, and applies cleanly to local + hosted. (Alembic is Python-native but
we're SQL-on-Supabase; the Supabase CLI is the lower-friction fit. If Genie prefers Alembic, that's
acceptable IF it manages the same SQL — but Supabase CLI is the recommendation.)

### A.2 Set up
- `supabase/migrations/` directory, committed to git.
- **Retro-fit the existing schema as migration 0001.** Today's `models/database.py` SCHEMA_SQL +
  `supabase_service.ADDITIONAL_SQL_FUNCTIONS` become `0001_initial_schema.sql` (the current state, so
  the migration history starts from a known baseline). `models/database.py` becomes documentation /
  seed reference, no longer the source of truth for DDL.
- Each migration: forward SQL + a commented `-- ROLLBACK:` block (Supabase CLI doesn't auto-generate
  down-migrations; document the reverse so it's reversible by hand if needed).
- **README in `supabase/migrations/`**: how to create, apply locally, apply to hosted, and the rule
  "never edit an applied migration — always add a new one."

### A.3 Acceptance for Part A
- `0001_initial_schema.sql` reproduces the current DB from scratch (verify: fresh Supabase project +
  apply -> same tables/functions as today).
- Migration process documented; no more console SQL.

---

## PART B — #1: First signal slice (`user_loved`)

### B.1 Migration `0002_signals_core.sql`
Minimal subset of the data model — just enough to capture ONE signal end-to-end. (Full §16 comes
later, as more migrations.)

```sql
-- sources registry (seed first_party)
CREATE TABLE source (
  source_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key           TEXT UNIQUE NOT NULL,
  display_name  TEXT NOT NULL,
  source_type   TEXT NOT NULL,       -- first_party | third_party_api | ... | derived
  trust_weight  FLOAT NOT NULL DEFAULT 1.0,
  legal_basis   TEXT NOT NULL,       -- 'user_consent' for first_party
  active        BOOLEAN NOT NULL DEFAULT true
);
INSERT INTO source (key, display_name, source_type, trust_weight, legal_basis)
VALUES ('first_party', 'First Party (app users)', 'first_party', 1.0, 'user_consent');

-- signal_type registry
CREATE TABLE signal_type (
  signal_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key            TEXT UNIQUE NOT NULL,
  category       TEXT NOT NULL,      -- explicit_user | behavioral | third_party_agg | derived
  value_kind     TEXT NOT NULL,      -- numeric | enum | json | boolean
  enum_values    TEXT[] ,
  decay_policy   TEXT NOT NULL DEFAULT 'none',
  description    TEXT
);
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description)
VALUES ('user_loved','explicit_user','enum', ARRAY['loved'], 'exp_180d',
        'User explicitly loved a place');

-- signal fact table (subset of §3.4; place_id nullable so we can capture before place graph exists)
CREATE TABLE signal (
  signal_id      UUID PRIMARY KEY,            -- CLIENT-GENERATED (idempotency key)
  place_ref      TEXT,                        -- venue_id/name from current itinerary (pre-entity-resolution)
  place_id       UUID,                        -- FK later, once place graph exists; nullable now
  source_id      UUID NOT NULL REFERENCES source(source_id),
  signal_type_id UUID NOT NULL REFERENCES signal_type(signal_type_id),
  user_id        TEXT,                        -- pseudonymous (Supabase sub or debug id)
  trip_id        TEXT,
  value_numeric  DOUBLE PRECISION,
  value_text     TEXT,
  value_json     JSONB,                       -- includes party_context (§16.5) later
  captured_at    TIMESTAMPTZ NOT NULL,        -- when user acted (client clock)
  ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  provenance     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_signal_place_ref ON signal(place_ref);
CREATE INDEX idx_signal_type_time ON signal(signal_type_id, captured_at);
-- ROLLBACK: DROP TABLE signal; DROP TABLE signal_type; DROP TABLE source;
```

Notes: `place_ref` (text) lets us capture *now* against the current itinerary's venue name/id, before
the canonical `place` graph + entity resolution exist. Later migration adds `place_id` FK + backfills.
`signal_id` is client-generated — the idempotency contract.

### B.2 Server: models + ingest endpoint
- **Pydantic model** `SignalIn` (in `models/schemas.py`):
  `{ signal_id: str(UUID), signal_type: str, place_ref: str, value_text?: str, value_numeric?: float,
     value_json?: dict, captured_at: datetime, trip_id?: str }`
  (server fills user_id from auth, source_id from 'first_party', ingested_at, provenance).
- **DB methods** on BOTH backends (behind `db_provider`):
  - `database_service` (in-memory): `record_signal(user_id, sig) -> {status}` storing in a dict keyed
    by `signal_id` (dedupe on repeat).
  - `supabase_service`: `record_signal(...)` -> resolve `signal_type_id` (cache the lookup),
    `INSERT ... ON CONFLICT (signal_id) DO NOTHING` (idempotent upsert).
- **Endpoint** in a new `routers/signal_router.py`, mounted in `main.py`:
  - `POST /signals` — accepts a **batch**: `{ "signals": [SignalIn, ...] }` (batch from day one,
    because the offline queue in SPEC-02 will sync batches; single is just batch of 1).
  - Auth: `Depends(get_current_user_id)` — user_id from token, never client body (reuse existing
    security). Validate `signal_type` exists (reject unknown types with 422).
  - Idempotent: re-POSTing the same `signal_id` is a 200 no-op, not a duplicate.
  - Consent check: **stub for now** (a `require_consent('behavioral_capture')` hook that currently
    passes; wired for real in a later spec). Leave the seam.
  - Returns `{ "accepted": N, "duplicates": M }`.

### B.3 Flutter: the emitter (THE POINT — don't skip)
- **Model** `lib/data/signal.dart`: `Signal` with `signalId` (generate via `uuid` pkg),
  `signalType`, `placeRef`, `valueText`, `capturedAt`, `tripId`. `toJson()` matching `SignalIn`.
- **Repository** method in `repositories.dart`: `Future<void> sendSignals(List<Signal>)` ->
  `POST /signals`.
- **UI wiring:** on the ActivityCard, add a lightweight **"heart loved"** affordance (a tap — jazzy not
  required, just functional). On tap:
  1. build a `Signal(signalType:'user_loved', placeRef: node.venueId ?? node.venueName,
     valueText:'loved', capturedAt: now, tripId: tripId, signalId: uuid.v4())`,
  2. call `sendSignals([sig])` fire-and-forget (errors swallowed for now; SPEC-02 adds the offline
     queue so this becomes "enqueue" instead of "send").
  - Add `uuid: ^4.x` to pubspec.
- **Important:** keep the emit call **abstracted behind a `SignalService`** so SPEC-02 can swap
  "send immediately" -> "enqueue locally, sync later" without touching the UI. This is the seam that
  makes offline work later.

### B.4 Tests
- **Python (pytest):**
  - `POST /signals` with a valid `user_loved` -> 200, `accepted:1`; row present (in-memory).
  - Re-POST same `signal_id` -> 200, `duplicates:1`, still one row (idempotency).
  - Unknown `signal_type` -> 422.
  - No auth -> 401 (reuse existing auth-guard pattern).
- **Flutter (mocktail):**
  - `SignalService.emit('user_loved', node)` calls `repository.sendSignals` with a well-formed
    `Signal` (correct `signal_type`, `place_ref`, a UUID `signal_id`).
  - Repository posts to `/signals` with the batch body shape (guard the contract like the existing
    `repositories_test`).
- Existing suites (21 py / 14 dart) stay green.

### B.5 Acceptance for Part B (definition of done)
1. Migrations `0001` + `0002` apply cleanly to a fresh Supabase project.
2. Tapping "loved" in the Flutter app (against the in-memory backend) -> `POST /signals` 200 -> row
   recorded; re-tap/retry does not duplicate.
3. Same works against Supabase when creds are set (idempotent upsert).
4. All tests green (py + dart), including the new idempotency test.
5. `SignalService` seam exists so SPEC-02 can make it offline without UI changes.

---

## Explicitly OUT of scope (later specs, don't gold-plate now)
- Offline queue / sync (SPEC-02 — the hard one).
- `trip_party`/`party_context` (SPEC-03) — capture without it for now; `value_json` is ready for it.
- Other signal types (behavioral reroute/dwell, etc.) — same pattern, added after this round-trips.
- Entity resolution / `place` graph — `place_ref` text is the placeholder.
- Fused scoring / aggregation.
Adding those now, before the round-trip is proven, is the failure mode. One signal, end-to-end, first.

## Review checklist (for the human/second-agent review before merge)
- [ ] `signal_id` is client-generated and the server upsert is genuinely idempotent (test proves it).
- [ ] user_id comes from the verified token, NEVER the request body (no IDOR regression).
- [ ] Works on BOTH backends behind `db_provider`; tests don't require live Supabase.
- [ ] The Flutter emit is behind `SignalService` (offline seam intact).
- [ ] Migration `0001` truly reproduces current schema (no drift).
- [ ] No hand-run console SQL introduced; everything is a migration file.
