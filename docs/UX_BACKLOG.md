# Travel Buddy — UX Backlog (ideas adopted from external UI/UX spec v2.0)
*Source: external UI/UX specification, Aug 2026. That doc's purpose was UI/UX ideation for the app
we are already building — NOT re-architecture. Ideas are merged into our existing capability model
(VISION §11). Architecture is unchanged (see §0).*

## 0. Architecture decisions NOT changing (read first)
The source doc proposed a from-scratch stack. Our stack is built, tested, and staying. Do **not**
migrate these — the cost is rewriting proven code for no product benefit:

| Source doc proposed | We keep | Why |
|---|---|---|
| Isar (NoSQL) for offline | **SQLite / `sqflite`** (`offline_database.dart`) | Outbox + cache proven: 11 offline tests, exactly-once sync, crash recovery, backoff+jitter |
| `LocalSyncEvent` queue schema | **`outbox` table** (state/attempts/next_retry_at) | Same contract already implemented, plus typed error classification |
| `NotifierProvider` ("StateNotifier obsolete") | **`StateNotifier`** (`ItineraryController`) | Soft-deprecated ≠ broken; 29 green tests. Migrate later, if ever |
| New folder layout (`core/db`, `data/repositories`) | **current `core/`, `data/`, `offline/`, `features/`** | Working; churn adds risk, not value |

Also **rejected** from the source doc:
- **Optimistic local reroute reflow while offline** — SPEC-02 §B.4 forbids this. Server owns
  re-planning; local optimistic reflow creates divergent state. Offline we capture the *intent* as a
  signal and defer. (Optimistic is fine for ❤/dislike, never for reroute.)
- **Continuous background GPS + battery polling** — a companion that flattens the phone by 3pm is
  worse than useless; in low-connectivity regions the phone is the user's lifeline. Poll on
  foreground/resume. **Battery is a first-class design constraint.**
- **"Generate complete runnable files, zero placeholders"** as an agent rule — empirically produced a
  bug class every time (interpolation escapes, missing widgets, unwired lifecycle, string-matched
  exceptions). We build in small vertical slices with review.

---

## 1. Adopted ideas, prioritized

### P1 — Offline Vault / Rescue Pack  ⭐
Implements **capability #7 (calm in the unexpected)**. Full spec: `docs/specs/SPEC-04-offline-vault.md`.
The one genuine *gap* the source doc exposed: our specs covered offline **data sync** thoroughly but
never asked "what does the user need to **do** when stranded?"
The thin hotel rescue entry exists, but it still chooses the first hotel-like
node rather than the current or next date-appropriate stay.

### P1 — Map-first split shell (hero screen IA)
Spatial context always visible, timeline a thumb-drag away.
- `DraggableScrollableSheet`, snaps at **18% / 45% / 92%**.
- Translucent floating top bar: trip status • party mode • network state • vault trigger.
- **Adopt with the existing placeholder map**; real tiles later (P3).
- Cheap (no map dependency) and the right frame for every on-trip capability.

### P2 — Side-by-side swap comparison (`SwapSheet`)
**Capability #2.** Original vs proposed alternative showing the **delta**: time, distance, cost, and
**"climate comfort"** (steal the term). Confirm → haptic → local update → queued sync.

### P2 — `AudienceBadge` + quick-swap sheet
**Capability #1.** Makes `trip_party` (DATA_MODEL §16) visible: shows active party mode
("Family — kids 3, 6"); tap to adjust **fatigue / dietary / transport** mid-trip.

### P2 — Proactive context banner
**Capability #2**, proactive not reactive. SPEC-29 now renders provider-backed
weather alerts above the timeline with provenance and a Review action. Climate
comfort remains UX polish; random traffic and synthetic transit must never
become alert copy.

### P3 — `SplitGroupCard` — split itineraries for diverging desires
**Capability #6**, made visible: "Group A: Old Souk / Group B: Mall, reconverge 17:00." Almost nobody
has this. Depends on the multi-preference optimizer → post-Laos.

### P3 — `TrapScoreIndicator` + `LocalAlternativeChip`
**Capability #5** (anti-regret): subtle confidence indicator + inline "locals rate the one 5 min
further much higher." Needs the fused place-quality view first.

### P3 — Real offline maps (MapLibre + `.mbtiles`)
The right long-term call — true offline maps, no Google key, aligns with our offline USP. Meaty
integration: **post-Laos**, behind the existing map interface.

### P4 — Design-token consolidation
Their token set (status colours on-time/reroute/alert; sheet radius 24; ambient micro-shadows; 4pt
grid) is close to ours but more complete. Fold in when the designer engages.

---

## 2. Sequencing rule (important)
**UX polish does not capture moat data.** The spine work above is shipped. The
remaining product order is:

1. Preserve evidence-backed alerts (SPEC-29 landed; no synthetic transit).
2. Date-scoped itinerary grouping is on main (Windows Sep 4). Date-aware stay
   selection remains unverified.
3. Make hearts durable and await `syncOnce()` before showing status counts.
4. Create real Laos trips (SPEC-32) instead of stamping destinations onto the
   Dubai template.

Full Vault and the map-first shell remain post-field-test unless spare capacity
appears.

If it's full Vault vs the October spine (identity, card, anchors), **the
spine wins.** Behavioral signals that are already registered still beat
polish.

## 3. Provenance
Kept from the source doc: Vault concept, native-script address card, climate-comfort delta,
split-group visualization, map-first IA. Its architecture section was written without knowledge of
our codebase and is superseded by §0.
