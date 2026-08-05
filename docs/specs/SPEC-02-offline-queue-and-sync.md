# SPEC-02 — Offline-first event queue + sync
*Implements roadmap item #2. Depends on SPEC-01 (idempotent `POST /signals`, `SignalService` seam).*
*Goal: signals and itinerary reads survive low/no connectivity, then sync exactly-once. This is what
makes the Laos trip produce the moat data — and it's USP #7 (offline resilience).*

## Why this is the riskiest spec
Failure here is **silent**: events vanish or duplicate, and you don't find out until you're home with
a corrupted dataset. Every requirement below exists to prevent a specific silent-loss mode. Do not
"simplify" the queue semantics.

## Non-negotiable invariants
1. **Never lose a user action.** A tap is persisted to local disk *before* any network attempt.
   If the app is killed, the event survives.
2. **Exactly-once server effect.** At-least-once delivery + server idempotency (SPEC-01's
   client-generated `signal_id`) = exactly-once effect. Never dedupe by "did the POST succeed?" alone.
3. **Never block the UI on network.** Enqueue is synchronous-fast and local; sync is background.
4. **Offline reads work.** The current trip's itinerary + venue data are readable with zero network.
5. **Clock skew is expected.** Trust the *device* clock for `captured_at` but record it as such; never
   let the server overwrite it (§5 freshness depends on when the user actually acted).

---

## PART A — Local persistence layer (Flutter)

### A.1 Storage choice
Use **`sqflite`** (SQLite) for the queue + cache. Rationale: durable, transactional, queryable,
survives app kill; `shared_preferences` is not suitable for a queue (no transactions, size limits),
and Hive/Isar add heavier deps. Add `sqflite` + `path` to pubspec. (On Flutter **web** sqflite needs
`sqflite_common_ffi_web` or a fallback — see A.4; web is only your dev-preview target, mobile is the
real target.)

### A.2 Local schema
```sql
-- outbound event queue
CREATE TABLE outbox (
  signal_id     TEXT PRIMARY KEY,   -- client-generated UUID = idempotency key
  payload_json  TEXT NOT NULL,      -- the full SignalIn JSON
  captured_at   TEXT NOT NULL,      -- ISO8601, device clock
  attempts      INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT,               -- ISO8601, for backoff
  last_error    TEXT,
  state         TEXT NOT NULL       -- pending | inflight | failed_permanent
);
CREATE INDEX idx_outbox_state ON outbox(state, next_retry_at);

-- read cache (offline reads)
CREATE TABLE cache_trip (
  trip_id     TEXT PRIMARY KEY,
  state_json  TEXT NOT NULL,        -- last known TripState
  cached_at   TEXT NOT NULL
);
CREATE TABLE cache_place (           -- venues seen in itineraries/search
  place_ref   TEXT PRIMARY KEY,
  data_json   TEXT NOT NULL,
  cached_at   TEXT NOT NULL
);
```

### A.3 `SignalService` (replaces SPEC-01's fire-and-forget)
The seam SPEC-01 created now becomes queue-backed. **UI call sites do not change.**
```
emit(signalType, placeRef, {valueText, valueNumeric, valueJson, tripId}) async
  1. build Signal with uuid.v4() + captured_at = DateTime.now().toUtc()
  2. INSERT into outbox (state='pending')      <-- durable BEFORE any network
  3. trigger a (non-awaited) sync attempt
  return immediately  // never await network
```

### A.4 Web fallback (dev only)
On `kIsWeb` without sqflite-web, fall back to an in-memory queue + `shared_preferences` mirror. **Log
loudly** that durability is degraded on web. Mobile (the Laos target) always uses SQLite.

---

## PART B — Sync engine

### B.1 Triggers
Attempt sync on: app start, app resume (foreground), connectivity regained
(`connectivity_plus` listener), after each `emit`, and a periodic timer (~60s) while foregrounded.
Never sync in a tight loop.

### B.2 Sync algorithm
```
syncOnce():
  if already running: return          // single-flight guard (mutex)
  batch = SELECT * FROM outbox
          WHERE state='pending' AND (next_retry_at IS NULL OR next_retry_at <= now)
          ORDER BY captured_at LIMIT 50
  if batch empty: return
  mark batch state='inflight'
  try:
    resp = POST /api/v1/signals { signals: [...] }     // SPEC-01 batch endpoint
    on 2xx:   DELETE those signal_ids from outbox      // server is idempotent; safe
    on 401:   mark 'pending', stop sync, surface re-auth (do NOT drop events)
    on 4xx (validation, e.g. 422):
              mark state='failed_permanent', last_error=...   // never retry forever
    on 5xx / timeout / network error:
              attempts++, state='pending',
              next_retry_at = now + backoff(attempts)
  catch anything:
    same as 5xx path                                   // NEVER leave rows stuck 'inflight'
  finally:
    reset any lingering 'inflight' in this batch to 'pending'
```
- **Backoff:** exponential with jitter — `min(2^attempts * 2s, 15min)` + random 0-20%. Jitter matters
  (avoids thundering herd when a whole group regains wifi).
- **`inflight` recovery on startup:** any row left `inflight` from a crash -> reset to `pending`.
  (This is the classic silent-loss bug: crashed mid-POST rows never retried.)
- **Partial batch:** if the endpoint returns per-item results later, honor them; for now a 2xx means
  the whole batch was accepted (server dedupes), so delete all.

### B.3 Queue hygiene
- **Cap:** if outbox > 5,000 rows, stop accepting new *low-priority* signals and log a warning
  (protects a long offline stretch from unbounded growth). Never silently drop *behavioral* signals.
- **`failed_permanent` rows are kept**, not deleted — they're diagnostic evidence, and you'll want
  them after Laos. Expose a count in the debug view (B.5).
- **Never delete on "looks stale."** Only 2xx or permanent-4xx removes/retires a row.

### B.4 Offline reads
- `TripRepository.getTrip`: on success -> write `cache_trip`; on network failure -> **read from cache**
  and return with a `fromCache: true` marker so the UI can show a subtle "offline — showing last
  known" banner. Same pattern for venue/search data.
- The itinerary screen must render fully from cache with **zero network**.
- **Mutations while offline:** structural events (swap/cancel) need the server's re-planning. Offline,
  do NOT fake a reroute. Instead: enqueue the *intent* as a signal (so the data is captured), show
  "we'll refresh this when you're back online," and keep the itinerary as-is. **Do not attempt local
  re-planning** — divergent local vs server state is a far worse bug than a deferred update. (Local
  optimistic edits are a future spec, only if field testing shows it's needed.)

### B.5 Debug/observability view (small, but do it)
A hidden Profile -> "Sync status" screen showing: pending / inflight / failed_permanent counts, last
sync time, last error. **You will need this in Laos** to know whether data is actually flowing. This
is 30 minutes of work that saves the trip's data.

---

## PART C — Server side (small additions to SPEC-01)
- Endpoint already idempotent + batch — no change needed if SPEC-01 was built to spec.
- Add: accept `captured_at` from client and **store it verbatim** (device clock); `ingested_at` is
  server-side. Never overwrite `captured_at`.
- Add: tolerate `captured_at` skew (accept timestamps up to, say, 30 days old and slightly in the
  future) — long offline stretches are normal. Record skew in `provenance` if extreme.
- Return `{accepted, duplicates, rejected:[{signal_id, reason}]}` so the client can retire
  permanently-bad rows precisely.

---

## PART D — Tests (this is where offline bugs get caught)
**Flutter (mocktail + in-memory sqflite):**
1. `emit` with network **down** -> row in outbox (`pending`), UI call returns immediately, no throw.
2. Connectivity restored -> sync posts the batch -> outbox empty.
3. **Duplicate safety:** sync where POST succeeds but the "delete" is interrupted -> next sync re-posts
   the same `signal_id`; assert client tolerates the duplicate response and clears the row.
4. **Crash recovery:** row left `inflight` -> on startup it resets to `pending` and is retried.
5. **Backoff:** on 5xx, `attempts` increments and `next_retry_at` is in the future; row not lost.
6. **Permanent failure:** 422 -> `failed_permanent`, not retried, row retained.
7. **401:** events are NOT dropped; sync halts.
8. **Offline read:** `getTrip` with network down returns cached trip with `fromCache: true`.
9. **Ordering:** batch is sent oldest-`captured_at` first.
10. Single-flight: two concurrent `syncOnce()` calls -> only one POST.

**Python:** `captured_at` is preserved verbatim; old timestamps accepted; malformed -> itemized
`rejected`, not a 500 for the whole batch.

**Manual (airplane-mode drill — do this before Laos):**
- Airplane mode -> tap loved on 5 venues -> force-kill app -> reopen -> still 5 pending -> enable network
  -> all sync, outbox empties, 5 rows in Supabase, no duplicates.

## Acceptance (definition of done)
1. Airplane-mode drill above passes end-to-end on a real device.
2. All 10 Flutter offline tests + Python tests green; existing suites unaffected.
3. Itinerary screen renders from cache with network off.
4. Sync-status debug view shows accurate counts.
5. No code path deletes a queued event except 2xx or itemized permanent rejection.

## Out of scope (deliberately)
- Local optimistic re-planning / conflict resolution (see B.4 rationale).
- Offline map tiles (nice-to-have; the itinerary + venue data matter more).
- Background sync while app is *terminated* (iOS/Android background tasks) — foreground+resume is
  sufficient for the field test; revisit later.
- Multi-device sync conflict handling.

## Review checklist
- [ ] Event persisted to SQLite BEFORE any network call (kill-the-app test proves it).
- [ ] `inflight` rows recovered on startup (no permanently-stuck events).
- [ ] Backoff has jitter and a cap; retries never infinite-loop.
- [ ] Only 2xx / permanent-4xx removes a row; 401 and 5xx never drop data.
- [ ] `captured_at` is device-clock and never overwritten server-side.
- [ ] UI never awaits the network on emit.
- [ ] No local re-planning fakery (offline structural intent is captured, not simulated).
- [ ] Sync-status view exists and is accurate.
