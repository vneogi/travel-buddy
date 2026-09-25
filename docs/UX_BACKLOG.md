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
The thin Hotel Rescue shortcut was tried and rejected by the owner on Sep 4:
it duplicated the driver-card action already available on the hotel booking.
Remove the shortcut; retain offline itinerary/place caching and the hotel
booking's driver card. A future full Vault needs fresh user evidence before it
earns a global entry point.

### P1 — Map-first split shell (hero screen IA)
Spatial context always visible, timeline a thumb-drag away.
- `DraggableScrollableSheet`, snaps at **18% / 45% / 92%**.
- Translucent floating top bar: trip status • party mode • network state • vault trigger.
- **Adopt with the existing placeholder map**; real tiles later (P3).
- Cheap (no map dependency) and the right frame for every on-trip capability.

### P1 — Multi-city Laos corridor
The Oct field trip is one journey across Vientiane, Vang Vieng, and Luang
Prabang, not three unrelated trip cards. Add cities with independent date
ranges to one trip and group the itinerary into collapsible city/day sections.
Past sections collapse without deleting their history. This needs an owning
spec for corridor ordering and stay/transport boundaries; it must not be
implemented by relabeling one city's venues. SPEC-36 now owns the first
northbound slice and explicitly refuses synthetic transfer and stay claims.
Implementation is on `main` via PR #55 (`1f2c43d`).

### P1 -- Phone-independent field-test delivery

SPEC-37 owns the delivery gate after SPEC-36: stable hosted HTTPS API,
installable phone artifact, online corridor proof, then a cold-reopen
airplane-mode drill with USB and local tunnels disconnected. This work is ahead
of visual polish because a laptop-tethered demo cannot accompany the traveller.

### P1 -- Public-release privacy and account controls

SPEC-43 owns the release foundation after the Laos build. The visible mobile
surfaces are:

- a real sign-out that stops sync, revokes the session, and clears prior
  identity data rather than only navigating;
- `Export my data`, `Delete account`, and `Clear offline data`, each with
  progress, retry, and a completion receipt;
- separate, plain-language choices for optional analytics, personalization,
  location features, and marketing;
- masked booking references and private notes with explicit reveal;
- an AI disclosure and a clear distinction between sourced facts,
  deterministic answers, and model-phrased answers;
- privacy-safe notification previews and owner-authorized deep links before OS
  push exists;
- an adult-account position with coarse family age bands, no child identity,
  and no child-level behavioral profile.

These controls precede the first non-owner build. They are not visual polish:
without them, account switching, deletion, consent, and restricted data have no
usable product contract.

### P2 — Side-by-side swap comparison (`SwapSheet`)
**Capability #2.** Original vs proposed alternative showing the **delta**: time, distance, cost, and
**"climate comfort"** (steal the term). Confirm → haptic → local update → queued sync.
The Sep 5 field run also requested spatial context for previous, current, next,
and candidate stops. Put that map in this comparison surface; do not leave a
blank decorative map panel.

### P2 — Inspectable recommendation reasons
Trip creation and swap should distinguish editorial recommendation from paid
placement. Candidate reasons can include party fit, season/time fit, popularity,
and a sourced hidden-gem signal. "Recommended" and "hidden gem" are claims, not
orange decoration: define the evidence and SPEC-17 envelope before rendering
them. Sponsored remains a separate disclosure and never masquerades as the
recommendation reason.

### P2 — `AudienceBadge` + quick-swap sheet
**Capability #1.** Makes `trip_party` (DATA_MODEL §16) visible: shows active party mode
("Family — kids 3, 6"); tap to adjust **fatigue / dietary / transport** mid-trip.

### P2 — Proactive context banner
**Capability #2**, proactive not reactive. SPEC-29 now renders provider-backed
weather alerts above the timeline with provenance and a Review action. Climate
comfort remains UX polish; random traffic and synthetic transit must never
become alert copy. SPEC-35 Phase A backend and Phase A2 in-app itinerary banner
are on main: fetch on load/resume/refresh, one departure reminder, no stack
with weather cards, local dismiss. OS push remains SPEC-27.

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

1. SPEC-40, SPEC-41 Phase A, SPEC-10 paste/scheduler, SPEC-25
   grounded trip-scoped Ask, G0 field-fix-2, and SPEC-45 Phase A are
   on `main`.
2. Phone-retest G0 plus SPEC-45 chrome on a signed APK from current
   `main`.
3. Finish SPEC-44 Phase A (PR #67) including CI PostgreSQL proofs of
   migration 0025. Do not apply 0025 to hosted until then.
4. SPEC-43 closes all twelve security/privacy gaps before another
   person uses the app or production LLM processing handles personal
   trip data.
5. SPEC-13, minimum SPEC-17 claims, and SPEC-20 make Bangkok a
   versioned city pack rather than another Python/Dart exception.
6. Only after Bangkok proves that factory, prototype SPEC-04 offline
   map artifacts on representative devices.
7. Only after SPEC-44 Phase A and the matching online command exist,
   consider a separate SQLite mutation-command outbox.
8. Only then resume map-first polish, multi-night hotel UI,
   inspiration, learned ranking, and broader consumer work.

Full Vault and the map-first shell remain post-reliability unless field evidence
changes the order.

If it's full Vault vs the October spine (identity, card, anchors), **the
spine wins.** Behavioral signals that are already registered still beat
polish.

## 3. Provenance
Kept from the source doc: Vault concept, native-script address card, climate-comfort delta,
split-group visualization, map-first IA. Its architecture section was written without knowledge of
our codebase and is superseded by §0.
