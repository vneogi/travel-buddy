# SPEC-58: Paste-Your-Plan Import

> Status: SLICE 1a MERGED (PR #375, `fbc4c0a`); SLICE 1b BRIEF WRITTEN
> (`docs/briefs/GENIE_SPEC58B_IMPORT_FLUTTER.md`, 2026-11-25; not yet sent).
> Earlier: 2026-11-24. Plain stops
> with no coordinates: owner chose (2026-11-24) that the server allows them on
> non-empty days, no travel check, labelled 'Not in our catalog, travel time
> not checked'; that is a SPEC-42 change, own brief to follow. Two slices:
> 1a backend, brief `docs/briefs/GENIE_SPEC58A_IMPORT_BACKEND.md` (ready to
> send); 1b Flutter, brief written after 1a lands (it depends on the
> endpoint shapes). Nothing implemented.
>
> Source: Nov 2026 competitive read, `docs/MARKET_STRATEGY.md`
> (Tripxcursion "Reality Check" and the "paste your ChatGPT plan" hook).
> Reuses SPEC-10 (provider-aware paste, locked anchors), SPEC-42
> (flexible spans, catalog direct add, trip-private uncatalogued add),
> SPEC-41 (hours and reachability checks) and SPEC-17 (claims sourced).
> Does not change any of them.

## 1. Goal

A traveller already has a plan from a chatbot, an agent, a blog or their
own notes. They paste it into Travel Buddy. The app turns it into a trip
that runs on the trip:

- Booking lines become **locked anchors** through the existing SPEC-10
  provider-aware paste.
- Stops that match the curated catalog become **flexible nodes**, only
  after the traveller confirms the match.
- Stops we cannot match become **trip-private plain rows** ("Not in our
  catalog") with no hours and no catalog identity.

The competitive point: the day stays feasible after import. A pre-trip
checker stops at a verdict; recovery (SPEC-41, SPEC-46, SPEC-42) is the
product, and the import is the front door.

## 2. Owner decisions

2026-11-23:

1. **Matching: confirm each one.** The app suggests a catalog match; the
   traveller accepts or rejects each. No auto-accept, including exact
   matches.
2. **Unmatched stops are plain rows**, no hours, no coordinates, no map,
   never recommended.
3. **Scope: catalog only.** No long-tail or OSM layer (still an open
   decision in `docs/MARKET_STRATEGY.md`).

2026-11-24 (after Genie's preflight found no name-only lookup, a per-add
reroute charge, and an existing trip-private add path):

4. **Matching uses a new small backend endpoint:** stop names plus region
   in, plain normalised-name match out. No embedding, no model call, no
   reroute quota. `/venues/search` is not used (it embeds the query).
5. **Plain rows are server-side trip-private nodes** through the existing
   SPEC-42 uncatalogued add (PR #77). They sync and survive sign-out. The
   stay length is traveller-stated (15 to 240 minutes), never invented.
6. **Commit is one batch import command** on the server. It runs the
   existing add checks per stop in order, uses one reroute in total, and
   returns per-stop results. Import creates a new trip with empty days;
   stops that do not fit a slot are listed unimported with the reason.
7. **Empty-start trips (2026-11-24, after Genie's preflight):** the create
   request gets an optional `start_empty` flag (default false) that skips
   the starter-day packing in the range create path. Request-model change
   only; no schema change, no new endpoint. Existing creates are unchanged.
8. **Accent-insensitive name match for the match endpoint only:** folds
   accents on Latin-script characters and leaves other scripts untouched.
   Import-only plain items get the same fold in their catalog-collision
   check so the two paths agree; single-item uncatalogued add is unchanged.

## 3. Design rules

- **Deterministic parse, on device.** The paste is split into day
  headings, time-prefixed lines and stop lines by plain rules, tested
  against fixtures of common chatbot, agent and blog formats. A model may
  later help with wording, never with the schedule (VISION section 24).
  Raw paste stays on the device and is never sent or logged.
- **Only stop names leave the device**, only when the traveller presses
  the match step, authenticated, to the name-match endpoint. The server
  does not log names; it logs counts only.
- **Bookings are not parsed here.** Booking-looking lines go to the
  existing SPEC-10 `extractBookingFromText` and booking sheet. No second
  booking parser.
- **Pasted times are hints, not locks.** A pasted clock time selects the
  named slot whose window contains it (existing `slot_from_time`). The
  batch command's per-stop checks (hours, reachability) decide whether it
  fits; a refusal is shown with its reason and is never silently changed.
  No time means the traveller picks a slot chip. An unplaced stop is
  listed, not guessed.
- **Every row is sourced or labelled.** Matched rows carry catalog
  provenance (SPEC-17). Plain rows say "Not in our catalog" in the
  import review and keep the existing "Added by you" rendering on the
  itinerary. Never an invented hour, place or price.
- **A rejected exact catalog match cannot become a plain row.** The
  uncatalogued add refuses a name that collides with a catalog venue
  (`catalog_match`). The review offers rename or drop, never a silent
  bypass.
- **No outcome signal in slice 1.** Accepted and rejected matches stay on
  the device. Emitting them as decision-outcome signals needs the SPEC-43
  consent screen and grant ledger (later brief).

## 4. Flow (end to end, across both slices)

1. Entry: one "Paste a plan" action on trip creation (no new home card,
   per SPEC-51).
2. Traveller pastes text and picks the region and start date (no region
   or date is guessed). Empty or over-limit paste is refused locally:
   limit 60 stop lines and 14 day headings.
3. Parse preview: days and stops in order; "Not understood" lines are
   shown and not imported; booking-looking lines are set aside.
4. Match: one call sends the stop names and region; each stop gets a
   suggested catalog match or "Not in our catalog". The traveller
   accepts or rejects each. Slot chips fill any stop without a pasted
   time; plain rows get a traveller-pressed stay chip.
5. Bookings go through the SPEC-10 paste step as their own step.
6. Commit: a new trip with empty days is created, then one batch import
   command adds the confirmed stops. Per-stop results come back.
7. Result: a normal trip. Unimported stops are listed with reasons and
   can be copied out so nothing is lost.

## 5. Limits stated honestly (slice 1)

- Add only fills an empty named slot on an empty date: four slots a day
  (morning, lunch, afternoon, dinner), one stop each, no whole-day
  excursions. A pasted day with more than four placeable stops imports
  four and lists the rest as unimported ("no free slot"). Lifting this
  is SPEC-42 territory, not this spec.
- Plain rows are ordinary trip-private nodes: movable and cancellable
  like any, never offered by What Now or swap as a candidate (they are
  not in the catalog).
- What the Driver card and Open in Maps do for a trip-private node is
  existing behaviour and is only reported, not changed, in this spec.

## 6. Slice 1a (backend) acceptance

1. Name match returns, per name, an exact normalised match (or alias),
   otherwise up to three deterministic near suggestions, otherwise none.
   Same input gives the same output.
2. Zero embedding calls, zero `llm.complete`, zero reroute quota used,
   in the name-match endpoint.
3. Names are not present in logs; invalid or unregistered region and
   more than 60 names are refused before any work.
4. Batch import with N accepted stops uses exactly one reroute and
   bumps the trip version once.
5. Each item is checked by the same code as catalog `direct_add` or
   `uncatalogued_add` (reused, not copied). A refused item is reported
   with its code and copy; accepted items in the same batch still land.
6. If every item is refused, nothing is persisted and no quota is used.
7. No write to `venues_rag`, `venue_dish`, `venue_external_id` or
   taxonomy tables; plain items have null `venue_id` and
   `place_source=trip_private`.
8. Over-limit batch (more than 60 items) and invalid items are refused
   before persist.

## 7. Slice 1b (Flutter) acceptance (to be briefed)

Parser fixtures; booking lines routed to SPEC-10; accept and reject per
match; no commit before acceptance; plain rows carry the traveller's
stay choice; empty and over-limit pastes refused with no network call;
raw paste absent from every request and log; unimported list shown with
reasons and a copy action.

## 8. Non-goals

LLM parsing or LLM-written schedules; long-tail or OSM places; any
auto-accept; PDF, screenshot or OCR input (SPEC-39 stays deferred);
outcome signals for matches (SPEC-43 first); party context (SPEC-54);
more than one stop per named slot; any change to SPEC-41 or SPEC-10
feasibility rules.

## 9. Stop rules

Stop and write a question, do not widen scope, if:

- the name-match endpoint would need an embedding, a model call or more
  than the stop name and region;
- the batch command cannot reuse the existing direct-add and
  uncatalogued-add checks without copying or weakening them;
- returning per-stop results needs a breaking change to the
  `process_event` contract (report the options instead);
- creating a trip with all-empty days needs a schema change or a new
  endpoint (an optional `start_empty` request field is allowed);
- a test can only pass by weakening a SPEC-41, SPEC-42 or SPEC-10
  check, or by editing an existing test.

## 10. Open after slice 1

Signal capture for accepted and rejected matches (after SPEC-43 consent);
model-assisted wording for messy pastes (only with a fixture pack proving
no schedule is invented); more than four stops a day (SPEC-42); whether a
plain row may open a map by name (owner call on what a name search reveals).
