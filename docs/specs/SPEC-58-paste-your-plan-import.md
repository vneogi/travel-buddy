# SPEC-58: Paste-Your-Plan Import

> Status: SPEC WRITTEN 2026-11-23. Not implemented. Brief:
> `docs/briefs/GENIE_SPEC58_PASTE_PLAN_IMPORT.md` (slice 1, not yet sent).
> Owner decisions 2026-11-23 are in section 2.
>
> Source: Nov 2026 competitive read, `docs/MARKET_STRATEGY.md`
> (Tripxcursion "Reality Check" and the "paste your ChatGPT plan" hook).
> Reuses SPEC-10 (provider-aware paste and locked anchors), SPEC-34 and
> SPEC-40 (catalog and typed Add), SPEC-41 (hours and reachability checks)
> and SPEC-17 (claims stay sourced). Does not change any of them.

## 1. Goal

A traveller already has a plan from a chatbot, an agent, a blog or their
own notes. They paste it into Travel Buddy. The app turns it into a trip
spine that runs on the trip:

- Bookings in the paste become **locked anchors**, through the existing
  SPEC-10 provider-aware paste path.
- Stops that match our curated catalog become **flexible nodes**, but only
  after the traveller confirms the match.
- Stops we cannot match become **plain "not in our catalog" rows** with no
  hours, no coordinates and no recovery use.

The competitive point is that the day stays feasible after import, which a
pre-trip checker does not give. The import is the front door; recovery
(SPEC-41, SPEC-46, SPEC-42) is the product.

## 2. Owner decisions (2026-11-23)

1. **Matching: confirm each one.** The app suggests a catalog match for a
   pasted stop. The traveller accepts or rejects it. No automatic accept,
   including for exact matches. Acceptance is per stop, not per paste.
2. **Unmatched stops: plain rows.** A stop we cannot match, or the
   traveller rejects, stays as a row labelled "Not in our catalog". It has
   no hours, no coordinates, no slot and no map. Recovery, What Now and
   swap never use it as a candidate or as an anchor.
3. **Scope: catalog only.** No long-tail or OSM fallback layer. That stays
   an open decision in `docs/MARKET_STRATEGY.md`, not a silent default.

## 3. Design rules

- **Deterministic parse, on device.** Slice 1 splits the paste into day
  headings, time-prefixed lines and stop lines with plain rules, tested
  against fixtures of common chatbot, agent and blog formats. A model may
  help a later slice with wording, never with the schedule (VISION
  section 24). Raw paste stays on the device and is never sent to the
  server or logged.
- **Only stop names leave the device** for matching, and only when the
  traveller has pressed the match step. A name is a search key, not a
  record. If the matching call needs a new endpoint, that is a stop rule
  (section 8).
- **Bookings are not parsed here.** A line that looks like a booking
  (flight code, hotel confirmation, reservation time) is handed to the
  existing SPEC-10 provider-aware paste. This spec does not add a second
  booking parser.
- **Pasted times are hints, not locks.** A stop time in the paste is
  carried as the traveller's wish. Existing SPEC-41 and SPEC-10 checks
  decide whether it fits. A refused time shows the server's reason on the
  row and is never silently changed.
- **Every row is sourced or labelled.** Matched rows carry the catalog
  provenance already shown on cards (SPEC-17). Unmatched rows carry
  "Not in our catalog", never an invented hour, place or price.
- **No outcome signal in slice 1.** Accepted and rejected matches are kept
  on the device only. Emitting them as decision-outcome signals needs the
  SPEC-43 consent screen and grant ledger, which are a later brief (see
  `docs/MARKET_STRATEGY.md`, operations and data section).

## 4. Flow

1. Home or trip creation: "Paste a plan" (one entry point; not a new home
   card, per SPEC-51).
2. Traveller pastes text. Empty or over-limit paste is refused with a
   clear message. Limit: 60 stop lines and 14 day headings in one paste.
3. Parse preview: days and stops listed in order. Lines that are neither a
   stop nor a booking are shown under "Not understood" and are not imported.
4. Match step: each stop gets either a suggested catalog match (name,
   city, provenance) or "Not in our catalog". The traveller accepts or
   rejects each suggestion.
5. Booking lines go to the SPEC-10 paste flow as their own step.
6. Commit: accepted matches are added through the existing typed Add
   path; unmatched and rejected stops become plain rows on their day. The
   server validates each add (SPEC-41); refusals are listed with reasons.
7. Result: a normal trip on the existing itinerary. Plain rows are visibly
   different and are excluded from recovery.

## 5. Plain "not in our catalog" rows

- Label: "Not in our catalog". No hours, distance, slot or map button.
- Actions: rename, move to another day, delete. Nothing else in slice 1.
- Excluded from: What Now, swap candidates, the scheduler, Driver card
  (no catalog id) and Open in Maps.
- Included in: the day's list and the trip's text export, so the plan is
  still complete.

## 6. Acceptance tests (slice 1)

1. A chatbot-style paste with three days parses to the right days and
   stops in order; the preview matches a fixture.
2. A booking line is routed to the SPEC-10 paste, not to the stop list.
3. A stop line with no catalog match becomes a plain row with no hours,
   coordinates or map button.
4. A suggested match is not committed until the traveller accepts it. A
   rejected match becomes a plain row.
5. An accepted match goes through the typed Add path. A server refusal
   (hours or reachability) is shown on the row with its reason.
6. Empty paste and an over-limit paste are refused without a network call.
7. Raw paste is not present in any network request or log line.
8. Plain rows are absent from What Now and swap candidate lists.

## 7. Non-goals

- LLM parsing or LLM-written schedules.
- Long-tail or OSM places, and any "not in catalog but recommended" list.
- Auto-accepting any match.
- PDF, screenshot or OCR input (SPEC-39 stays deferred).
- Outcome signals for accepted or rejected matches (SPEC-43 first).
- Group or party context (SPEC-54 stays parked).
- Any change to scheduler feasibility rules.

## 8. Stop rules

Stop and write a question, do not widen scope, if:

- the match step needs a server endpoint that does not exist and would
  send more than stop names;
- a plain row would need a new backend field, migration or schema change;
- matching would need to store raw paste, even temporarily, on a server;
- a booking line cannot be routed to SPEC-10 without a new parser;
- an acceptance test can only pass by weakening a SPEC-41 or SPEC-10 check.

## 9. Open after slice 1

- Signal capture for accepted and rejected matches (after SPEC-43 consent).
- Model-assisted wording for messy pastes (only with the stop rules above
  unchanged and a fixture pack that proves no schedule is invented).
- Whether plain rows can ever open a map by name (needs an owner call on
  what a name search reveals).
