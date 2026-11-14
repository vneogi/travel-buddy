# Travel Buddy — UX Backlog (ideas adopted from external UI/UX spec v2.0)
*Source: external UI/UX specification, Aug 2026. That doc's purpose was UI/UX ideation for the app
we are already building — NOT re-architecture. Ideas are merged into our existing capability model
(VISION §11). Architecture is unchanged (see §0).*

## Oct 11 2026 field reprioritization

The older priority labels below record earlier UI ideation; they do not override
the current sequence in `PROJECT_STATUS.md`. Laos use plus 138 reviewed
Laos/China Gemini turns moved these surfaces to the front:

1. P0 current-surface hygiene is on main.
2. Broad, persistent, grounded trip Ask threads are on main.
3. What Now Phase A is on main: deterministic structured results in that thread.
4. Thin typed Ask-to-Add, Move, empty-day catalog Add, and uncatalogued trip-private Add are on main. Next product remainder: unknown-time excursions. SPEC-43 still gates non-owner use.
5. Operational card detail and current/next route guidance.

The map-first shell, Travelogue/Passport, social features, gamification,
offline tiles, and cross-trip memory are deferred. Drag/reorder/add and maps are
competitive table stakes; they are not the moat.

## Nov 14 2026 owner device findings (Zanzibar and Nungwi packs)

Context: the Stone Town (38 venues) and Nungwi/Kendwa (34 venues) catalogs are
loaded into hosted Supabase, Cloud Run is on revision `travel-buddy-00015-x8d`,
and the owner installed an APK rebuilt from main `206122a`. Device checks:

- The destination list offers Zanzibar and Nungwi (Zanzibar).
- A Nungwi trip (29 Dec 2026 to 2 Jan 2027, solo) seeded day 1 from Nungwi
  catalog venues only: Cholo's Beach by Bento, Kibanda, Nungwi Lighthouse,
  Le Macis.
- A Zanzibar trip (26 to 28 Dec 2026, friends of 6) seeded day 1 from Stone
  Town venues only: Malindi Fish Market, Mercury's Restaurant, Africa House
  Terrace, Passing Show.

None of the findings below blocks the December trip. They are product changes
to schedule when build time allows. Each needs an owning spec or spec amendment
before a Genie brief.

### F1 -- One "Create a trip" entry for single and multi-city trips

Observed: home shows a separate "Vientiane to Luang Prabang / Multi-city Laos
corridor" card above "Create a trip". Owner expectation: one create flow where a
trip is one city or several.

Direction: fold the corridor into the create flow. The destination step lets the
traveller pick one or more destinations in order, then dates per city (reuse the
per-segment ranges in `CorridorDateForm`). The Laos corridor becomes a preset
inside that flow, not a card on home. SPEC-36 rules stand: no synthetic
transfers or stays, and no relabeling one city's venues. The corridor stays
driven by the backend `supportedCorridors` list.

Out of scope here: combining non-corridor regions (for example Stone Town plus
Nungwi). They are separate regions on purpose because day plans do not cluster
across them. That needs geographic day clustering and its own spec.

Owners: SPEC-36 amendment plus SPEC-26 home snapshot. Dart-led; update
`spec36_corridor_test.dart` and the home tests.

### F2 -- Driver card in the local language for Tanzania

Observed: the Driver Card for a Tanzania venue is not in Swahili.

Root cause, verified on main `206122a`:

1. `languagePriority` in `mobile/lib/features/driver_card/driver_card_helpers.dart`
   handles Laos (`lo`, `th`, `en`) and Dubai (`ar`, `en`) only. Every other
   region falls back to `['en']`.
2. Neither `data/zanzibar_tanzania.json` nor `data/nungwi_tanzania.json` carries
   `name_local` or any landmark text, so the seed writes no `names_local` or
   `landmarks_local`. The card shows "Local name not available" and the English
   name.
3. The card chrome strings are English.

The seed side already maps both Tanzania regions to `sw`
(`CATALOG_LANGUAGES`, `REGION_LANGUAGES`). The client mirror is missing.

Direction:

- Add `sw` then `en` for the Tanzania regions in `languagePriority`, and add a
  test that the client priority agrees with the loader language map.
- Swahili uses Latin script, so the venue name is often the same as the roman
  name. The useful local content is the landmark and direction text a driver
  reads. Add per-venue Swahili landmark text with provenance per SPEC-12
  decisions 2 and 3: `generated` entries render as unconfirmed with the confirm
  affordance and never as the confident headline; only `field_verified`
  promotes. Never label unverified Swahili as verified.
- The owner can verify names and landmarks with locals during the trip, which
  feeds the `field_verified` moat data.

Owners: SPEC-12 amendment (region language priority table), data pass for
Swahili landmarks, Dart mirror.

### F3 -- Existing trips shown as markers in the date picker

Observed: when creating a second trip, the date picker shows no trace of the
first trip.

Wanted: like meeting invites in a calendar. Days already covered by another trip
are visibly marked. The marker never blocks creating an overlapping trip.

Direction: `showDateRangePicker` cannot decorate individual days, so wrap or
replace it with a range-select calendar that draws a marker (and optionally a
short trip label) on days covered by existing trips. Read from the local trips
list so it works offline and needs no new endpoint. Compare trip dates as
destination-local calendar dates (date-only, no time zone shift). Optionally show
a non-blocking note on the review screen ("Overlaps with <trip> on <dates>").
Apply to create trip and the corridor date form first.

Owners: SPEC-31 amendment (date scope) or a new small spec. Dart-only; widget
tests for marker rendering and for overlap not blocking create.

### F4 -- Catalog data notes from the same session

- Cholo's Beach by Bento is a beach bar. The planner placed it in the morning
  slot on a Nungwi day. **Planner fix on main** (`668bb6f`, PR #225): a venue
  with `category == bar` may only fill `afternoon_evening_tour`, enforced in
  the shared slot helpers used by generation and swap. Owner field verification
  of opening hours remains the durable catalog fix. A later bar start-time
  floor (for example not before 16:00) is still optional and not landed.
- The stops seen carry mostly the generic `leisurely` tag. Check whether the
  catalog `vibe_tags` are too generic to drive ranking and swap reasons. Not
  verified as a defect.

### Proposed order (planner)

Owner deferral 2026-11-14: frontend F1-F3 after Tanzania core; none of them
blocks the December trip.

1. F2 first: it affects the in-trip card and feeds verified-name data. Client
   priority plus tests are small; the Swahili landmark data pass is the larger
   part and needs owner verification on site.
2. F3: Dart-only, self-contained, no backend.
3. F1: needs the SPEC-36 and SPEC-26 amendment first.
4. F4 remainder: catalog hours and vibe_tags on the next catalog edit after
   field verification (bar morning-slot planner defect is closed).

---

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
   grounded trip-scoped Ask, G0 field-fix-2, SPEC-45 Phase A, and
   SPEC-44 Phase A are on `main` (`9a7b9d9`).
2. Owner phone retest of G0 plus SPEC-45 chrome is recorded
   2026-09-27. Thursday freeze uses APK `bd935bf2...` and Cloud Run
   `00012-8wv`.
3. Durable Ask threads, SPEC-46 What Now Phase A (`d1df944`), thin
   typed Ask-to-Add (`0344b4b`), thin typed Move (`e51513e`),
   empty-day catalog Add (`b6ddecf`), and trip-private uncatalogued Add
   (`05d917e`) are on `main`. Next product remainder is unknown-time
   excursions. Catalog place prompts and weather-day drill-down remain
   recorded SPEC-25 / SPEC-29 follow-ups. SPEC-43 still closes all
   twelve security/privacy gaps before another person uses the app or
   production LLM processing handles personal trip data.
4. SPEC-13, minimum SPEC-17 claims, and SPEC-20 make Bangkok a
   versioned city pack rather than another Python/Dart exception.
5. Only after Bangkok proves that factory, prototype SPEC-04 offline
   map artifacts on representative devices.
6. Only after SPEC-44 Phase A and the matching online command exist,
   consider a separate SQLite mutation-command outbox.
7. Only then resume map-first polish, multi-night hotel UI,
   inspiration, learned ranking, and broader consumer work.

Full Vault and the map-first shell remain post-reliability unless field evidence
changes the order.

If it's full Vault vs the October spine (identity, card, anchors), **the
spine wins.** Behavioral signals that are already registered still beat
polish.

### P2 -- Engagement after Laos (accepted 27 Sep 2026)

Not a redesign. SPEC-45 Phase A already landed the itinerary chrome.
Explore after field evidence. Owners:

- What Now, Rescue, Hungry now, temporary situation chips: SPEC-46
- Transfer/arrival card, place-detail beyond placeholder: SPEC-45
- Contextual one-tap questions, trust copy, no gamification:
  DATA_FLYWHEEL_OPERATING_MODEL.md and SPEC-47
- Travelogue and Route Passport: VISION section 14
- Hostel arrival pack: SPEC-04 / SPEC-45 after SPEC-43 G1

Still rejected: social feed, DMs, people nearby, points, background GPS,
generic review forms, auto-replan from warnings, dietary badges,
unsourced hidden-gem labels.

## 3. Provenance
Kept from the source doc: Vault concept, native-script address card, climate-comfort delta,
split-group visualization, map-first IA. Its architecture section was written without knowledge of
our codebase and is superseded by §0.
