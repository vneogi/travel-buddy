# Travel Buddy -- UI/UX Implementation Specifications

**Draft for product/engineering review  |  15 Nov 2026**  
**Scope:** the recommendations from the repository review, aligned to the existing Flutter + FastAPI architecture and current specs. These are proposals, not landed features.


> Repo status 2026-11-15: penciled proposals for UX-48 through UX-56.
> Not yet owning specs on disk. Sequence and open-items live in
> `docs/PROJECT_STATUS.md` and `docs/UX_BACKLOG.md`. UX-49 client
> language priority (F2) and UX-52 date markers (F3) are already on
> main; remaining work under those numbers is noted in the backlog.
> The team draft used SPEC numbers 48 to 56; they are written UX-NN
> here until each owning spec file exists in `docs/specs/` (docs
> hygiene rejects SPEC references with no spec file).

## Guiding constraints

- Preserve the product thesis: grounded, trip-scoped help when plans change, including weak/offline connectivity.
- The server remains authoritative for itinerary mutations. No optimistic offline reroutes or silent replanning.
- Render claims only when supported by sourced data. Do not infer live traffic, opening status, AC, distances, transit availability, or station names from missing fields.
- Preserve confirmed bookings and locked anchors. New behaviors must have explicit traveler confirmation.
- Treat SPEC-43 privacy/security gates as prerequisites for non-owner release and production processing of personal trip data.
- Keep mobile state offline-first; use existing SQLite caches and outbox contracts rather than creating a second sync system.

## UX-48 -- On-trip glanceability and connective timeline

**Goal:** Let a traveler quickly see what is happening now, what follows, and whether there is enough time to get there.

**Scope:** improve the current `ActivityCard` and timeline presentation, without changing schedule generation or introducing a map-first shell.

**UX requirements**
1. Give the active stop stronger hierarchy using existing design tokens: clear "NOW" label, title, local time, and one primary action. Avoid an oversized card that pushes the next stop below the fold.
2. Promote the next stop when no node is currently active: label it "UP NEXT" and show destination-local start time and available buffer.
3. Add a compact connector between consecutive eligible activity cards. Show only a transit duration/mode when backed by a trusted route result; otherwise show no estimate rather than a fabricated one.
4. If a server-provided feasibility result identifies a schedule conflict, show the existing warning treatment and a useful action. Do not calculate a new warning from guessed travel time.
5. Keep connectors out of hotel continuation rows and avoid duplicate connectors across city sections.

**Implementation notes**
- Primary files: `mobile/lib/widgets/activity_card.dart`, `mobile/lib/features/itinerary/itinerary_screen.dart`, `mobile/lib/widgets/city_section.dart`; reuse `warning_helpers.dart`, `current_window.dart`, and existing render/trust patterns.
- Prefer a small `TransitConnector` presentation widget whose input is already-resolved display data. Do not couple it to a new network call per row.
- Preserve current stable node keys and list behavior during swap/cancel/reflow.
- Define accessibility semantics for "Now", "Up next", and any warning; maintain 44dp touch targets and text scaling.

**Acceptance**
- Current and next states are distinguishable at a glance, including when the itinerary is cached/offline.
- A connector appears only when its mode/time has provenance; no fabricated "walk" or "drive" estimate.
- Existing itinerary reflow, booking locks, corridor grouping, and offline tests remain green.
- Long venue names and 200% text scaling do not cause horizontal overflow.

## UX-49 -- Driver card handoff ergonomics and Tanzania language support

**Goal:** Make the existing offline Driver Card easier to show to a local driver, and close the documented Tanzania language gap.

**UX requirements**
1. Add an explicit "Show to driver" presentation mode, reachable from the existing Driver Card. Use a large, high-contrast destination name and verified landmark/directions; include a clearly visible exit/restore control.
2. Do not assume a 180 deg rotation helps all handoffs. Prototype normal orientation first; offer rotation as an optional, reversible setting only if device testing confirms it is useful.
3. Brightness override is optional and must be temporary, permission-free where possible, and always restored on exit, navigation, app interruption, and error. Do not force maximum brightness automatically.
4. For `zanzibar_tanzania` and `nungwi_tanzania`, language priority should be Swahili then English, consistent with the catalog loader. Missing Swahili names/landmarks must fall back honestly to English and say local text is unavailable; do not generate or imply verification.
5. Preserve SPEC-12 provenance tiers. Generated/unconfirmed strings cannot render as confirmed local claims.

**Implementation notes**
- Primary files: `mobile/lib/features/driver_card/driver_card_screen.dart`, `driver_card_helpers.dart`, `render/fact_view.dart`, plus language-priority tests.
- Repository UX backlog says the client language-priority fix is already on main; verify current branch before repeating it. The remaining work is field-verifiable Swahili landmarks/content and optional presentation mode.
- Keep the card renderable from the current SQLite cache with zero network calls.

**Acceptance**
- Mode is one tap in and one tap out, works offline, and is readable with large text.
- Brightness/orientation state always restores after exit and lifecycle interruption.
- Tanzania follows `sw` then `en`; missing or unverified data is labeled accurately.
- Tests cover locale priority, provenance display, cache-only rendering, and cleanup on disposal.

## UX-50 -- Inspectable swap comparison

**Goal:** Help a trip captain compare a proposed replacement with the current stop before confirming a swap.

**UX requirements**
- Present current stop and one candidate in a vertical comparison that fits a 360dp screen. Keep the existing search/list flow available.
- Show only supported dimensions: schedule fit/buffer, available route distance or duration with source/freshness, price band when known, accessibility/party fit when explicitly cataloged, and climate/indoor comfort only when explicitly sourced.
- Each dimension has "known", "not available", or an appropriately sourced value. Avoid a generic score or "better" claim without a defined evidence contract.
- Candidate reason text explains evidence (e.g. "fits before your 16:00 booking"), not opaque ranking.
- "Confirm swap" remains a distinct action. Show a confirmation summary and preserve locked bookings. "Next option" changes the comparison without mutating the itinerary.

**Implementation notes**
- Primary file: `mobile/lib/features/swap_sheet/swap_sheet.dart`; inspect `models.dart`, `VenueSearchResult`, `services/route_provider.py`, scheduling responses, and SPEC-17 envelopes before adding fields.
- Start client-only with values already present. Add backend fields only with a documented source, schema, freshness behavior, and tests. Do not add `climate_comfort` or travel deltas as guessed catalog values.
- Use semantic labels/icons and responsive vertical layout rather than a two-column table on narrow phones.

**Acceptance**
- No overflow at narrow widths or large text sizes.
- Missing data is omitted/labeled unavailable; no unsupported climate, price, popularity, or travel claims.
- Candidate browsing never mutates; a confirmed swap uses the existing authoritative command path and preserves anchors.
- Unit/widget tests cover locked stops, missing dimensions, and confirmation/dismissal.

## UX-51 -- Unified single-/multi-destination trip creation

**Goal:** Present one "Create a trip" entry point while keeping supported corridor boundaries explicit.

**UX requirements**
1. Home has one primary creation action. A supported corridor is a preset inside that flow, not a separate competing home card.
2. Destination step offers supported single regions and supported corridor presets; do not imply arbitrary multi-city combinations are supported.
3. Single destination reuses the existing guided create flow. Corridor preset reuses `CorridorDateForm` and per-segment dates.
4. Before submission, show destinations in order, dates per segment, party, and a clear review state. Explain that unsupported combinations cannot yet be combined.
5. Preserve existing trip creation, validation, error recovery, and accessible back navigation.

**Implementation notes**
- Primary files: `mobile/lib/features/home/home_screen.dart`, `features/create_trip/create_trip_screen.dart`, `widgets/corridor_date_form.dart`, routing and existing create tests.
- Use the backend-supported corridor registry as source of truth; do not hardcode a generic multi-city planner or introduce an undocumented `/corridors` endpoint.
- Follow `docs/UX_BACKLOG.md` F1 and SPEC-36/26. The backlog marks this direction as pending, not implemented.

**Acceptance**
- Home presents one clear create entry point.
- Single-city and supported corridor creation both succeed through the unified flow.
- Corridor sequence/date validation remains backend-authoritative; no synthetic stays or transfers are inserted.
- Tests cover preset selection, date validation, back navigation, and existing trip creation regressions.

## UX-52 -- Existing-trip date markers

**Goal:** Give non-blocking awareness of date overlap while creating another trip.

**UX requirements**
- Decorate dates covered by existing trips with a subtle marker and accessible label.
- On selection, show a concise overlap note with trip name and covered dates when available.
- Never disable dates or prevent an overlapping trip. Do not treat the marker as a booking conflict.
- Use cached trip summaries so the picker remains useful offline; show stale/cached status through the existing offline conventions.

**Implementation notes**
- Primary file: `mobile/lib/widgets/existing_trip_date_range_picker.dart` and trip summary/date model.
- Compare calendar dates as destination-local date-only values, not UTC instants. Respect each existing trip's region and the new trip's selected destination; test boundary cases around timezone conversion.
- The UX backlog reports overlap markers as closed on main (F3, 15 Nov 2026). Check current implementation/tests first; this spec is a verification checklist and only a change request if a remaining gap is found.

**Acceptance**
- Markers render from cached summaries and have accessible semantics.
- Overlap remains allowed; no creation request is blocked.
- Tests cover trip start/end boundaries, multi-day spans, timezones, offline cache, and multiple overlapping trips.

## UX-53 -- Situation chips in the existing Ask/What Now thread

**Goal:** Reduce typing when the traveler needs quick recovery while preserving the existing grounded trip-scoped Ask architecture.

**UX requirements**
- Offer a small horizontally scrollable set of context-relevant suggestions, such as "Too hot", "Rain shelter", "Quick break", and "Call it a day". Do not display unsupported options as executable capabilities.
- Chips prefill/submit a typed intent in the existing durable trip thread. The user can review what was asked; results render with the existing structured What Now presentation.
- A chip must return feasible choices or a clear "no grounded option found" state. Never create a place or mutate the schedule silently.
- Any add/swap/cancel action requires explicit review and confirmation. "Call it a day" must propose specific affected stops, not cancel them directly.
- Respect current trip/date/party context and network/offline state. Explain when a chip needs connectivity.

**Implementation notes**
- Primary files: `mobile/lib/features/chat/ask_entry_bar.dart`, `chat_screen.dart`, `what_now_bubble.dart`, and existing SPEC-25/SPEC-46 intent handling.
- Reuse the structured intent and response envelope already used by What Now; do not create a parallel assistant or a new endpoint unless the existing contract cannot express the request.
- Remove hard-coded "800m", "air-conditioned", or 45-minute assumptions unless the engine has trusted fields and deterministic rules for them.

**Acceptance**
- Chips are reachable above the keyboard, scrollable, and accessible.
- Each chip maps to a tested, closed intent; prompt and response persist in the existing thread.
- No result claims live weather/traffic or indoor/AC status without evidence.
- No itinerary mutation occurs until explicit confirmation; offline behavior is clear and safe.

## UX-54 -- Temporary party context and energy constraints

**Goal:** Let the trip captain temporarily explain a group's current needs without rewriting persistent party identity or altering locked commitments.

**UX requirements**
- Show the saved party context only if available and useful; do not expose children's exact ages publicly or unnecessarily.
- Offer temporary controls such as "Low energy" and "Prefer indoors" only when the recommendation engine can honor them. Clearly label the scope and expiry.
- A toggle affects future What Now/swap suggestions, not existing itinerary nodes, booking anchors, or schedule automatically.
- User can clear the temporary state at any time. Expiry should be explicit and destination-local; do not silently assume midnight if trip timezone is unavailable.

**Implementation notes**
- First validate the existing trip-party model and recommendation inputs. Keep temporary overrides client-local initially, scoped to trip and identity, and clear them on trip change/sign-out as appropriate.
- If server-side persistence is required for cross-device use, define consent, retention, ownership, and data minimization under SPEC-43 before schema changes.
- Do not add assumed filters such as "no open water" or "low walking" without curated attributes and deterministic behavior.

**Acceptance**
- Temporary state changes only the explicitly supported recommendation query and is visibly active.
- No state leaks between trips or identities; expiry/clear behavior is tested.
- Locked bookings and existing itinerary remain unchanged.
- UI explains when a constraint cannot be honored due to missing data.

## UX-55 -- Inter-city transfer information

**Goal:** Make known travel between corridor destinations visible without inventing transport arrangements.

**UX requirements**
- Where the traveler has added a transfer booking or confirmed details, show an inter-city transfer card in date order with mode, local departure/arrival time, origin/destination, and reference if provided.
- If no transfer is recorded, show a restrained "Travel between destinations" gap with an optional user action to add a booking; do not present an assumed train, station, departure, or arrival as fact.
- Local-script names and driver/station cards appear only when verified/provenanced and available offline.
- Transfers are distinct from activity recommendations and never auto-created by corridor generation.

**Implementation notes**
- Reuse existing booking anchors and booking types where possible. Inspect `models/schemas.py`, trip booking flows, SPEC-10, SPEC-36, and SPEC-12 before introducing a new `corridor_transit` node kind.
- If current booking model cannot represent station-to-station transfer details, propose a narrow schema amendment with migration/backward-compatibility plan; do not subclass `TripNode` speculatively.
- Render in the existing city/day timeline structure and maintain stable ordering/keys.

**Acceptance**
- Confirmed transfer booking details render offline from cache with local-time correctness.
- Missing transfer details are clearly absent, not synthesized.
- Adding/editing/deleting a transfer follows existing confirmation, ownership, and anchor rules.
- Corridor and single-city timelines remain compatible.

## UX-56 -- Offline readiness indicator

**Goal:** Tell travelers what is actually saved locally before connectivity is lost, without promising a complete offline city pack unless one exists.

**UX requirements**
- Show a compact status for itinerary cache freshness/connectivity, for example "Saved on this device" with a timestamp or "Offline; showing saved trip".
- A detail sheet may list verifiable local items: itinerary snapshot, cached place cards, pending signals, and last successful sync time.
- Distinguish "cached stops" from "100% offline ready." Do not claim maps, emergency contacts, all venues, or full city packs are downloaded unless those capabilities and data are actually present.
- Provide manual retry/refresh where appropriate; avoid background download prompts that consume mobile data/battery without consent.

**Implementation notes**
- Inspect `offline/offline_database.dart`, `sync_engine.dart`, `render/offline_state.dart`, and current cache schema before adding queries. Prefer existing cache metadata and bounded queries; never block the UI thread.
- A full offline pack/download feature is out of scope until its content set, size, licensing, freshness, and download behavior are specified.
- Pending outbox count is diagnostic, not a measure of offline readiness; present separately and with plain language.

**Acceptance**
- Indicator is accurate on fresh cache, stale cache, no cache, online, and airplane mode.
- Timestamp/freshness reflects actual cache metadata and no unverified "100%" claim is shown.
- Queries are bounded and do not delay opening the itinerary.
- Tests cover lifecycle refresh, stale cache, cache absence, and pending sync.

## Suggested sequencing

1. Verify completed backlog work first: UX-49 Tanzania language-priority client fix and UX-52 overlap markers are reported as landed in `docs/UX_BACKLOG.md`.
2. Prototype UX-48 and UX-53 as client changes using data/contracts already available.
3. Define evidence contracts before UX-50's comparison metrics or UX-54's recommendation filters.
4. Unify creation under UX-51 after aligning with SPEC-26/SPEC-36 status and the current supported corridor registry.
5. Add UX-55 only for traveler-entered/confirmed transfers; UX-56 should initially report existing cache status, not imply a full downloadable pack.

## Definition of done for each spec

- Owning spec/backlog status updated; implementation is sliced and reviewed against current code, not this draft alone.
- API/model changes are backward-compatible or have a migration and rollback plan.
- Widget, behavior, offline, timezone, and accessibility tests cover the acceptance criteria.
- Field/device verification is recorded separately from automated tests.
- No unsourced claims, silent mutations, cross-identity cache leakage, or unexpected network dependence.
