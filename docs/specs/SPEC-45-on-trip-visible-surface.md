# SPEC-45: On-Trip Visible Surface

> Status: PHASE A IMPLEMENTED on main (`7939565`, laptop Flutter
> `61b07d0`). Phone APK retest of this chrome is still open. Remainder
> of this spec (map tiles, Add/Move, GPS, SPEC-43 account chrome) is
> not this merge.
>
> Recorded 24 Sep 2026 from an external UX/product review of `d9f89ba`
> plus owner Android screenshots the same day. This spec owns **visible
> itinerary information architecture** after G0 schedule reliability.
> It does not own security, money storage, push transport, PDF intake,
> or city expansion.
>
> Depends on SPEC-22 (render/trust treatments), SPEC-17 (claims),
> SPEC-26 (home snapshot), SPEC-25 (Ask), SPEC-12 (driver card),
> SPEC-36 (corridor), SPEC-38 (focus/now), SPEC-41 (feasibility),
> SPEC-10 (bookings). Empty-day actions depend on SPEC-42 Add/Move,
> not SPEC-44 (backend integrity) and not this spec.

## Goal

Make the product look like the engine it already has: an **on-trip
recovery companion**, not a pre-trip planner with extra buttons.

A traveller opening the app on a narrow phone should, within a few
seconds, know:

- what to do now
- what is next
- whether today's plan is in trouble
- how to change one stop without hunting icons
- what the app knows, does not know, and will not change until they
  confirm

## Why a new spec

Most of the review maps onto specs that already exist. Those specs
keep ownership. What did not have a contract is the **itinerary
chrome** the owner actually used on 24 Sep 2026: dense cards, two Ask
entry points, raw `micro_location` slugs, debug booking labels,
composer covering Dinner, schedule banners without a next action,
hotel times without dates, swap lists without trade-offs.

`docs/UX_BACKLOG.md` remains the idea list. This spec is the
implementation contract for the visible-surface slice.

## What already exists (do not rebuild)

Preserve: corridor itineraries, locked bookings, swap/cancel with
confirm-before-mutate, hours-aware packing, offline itinerary and
driver-card cache, trip-scoped Ask, weather/departure banners,
local-script driver cards, hosted API, signed APK path.

Server still owns re-planning. Offline must not pretend it can
reflow. SPEC-02 still forbids optimistic itinerary mutation.

SPEC-38 already decided: home stays reachable; featured Now/Up next
opens the itinerary with `focus`. Do not add a global redirect away
from `/`.

## Decision map (review item to owner)

| Review ask | Owner | This slice? |
|---|---|---|
| Active trip above Create on Home | SPEC-26 remainder + this spec | Yes, layout only; reuse `featured_trip` |
| Time-aware greeting | SPEC-26 remainder | Yes, copy from existing snapshot/cache age |
| Timeline / Map command center | UX_BACKLOG P1 map-first shell | **Later.** Placeholder map only if it does not block G0. Real tiles are P3 MapLibre / `.mbtiles` |
| Card tap opens place details | this spec + activity_detail remainder | Yes |
| Overflow for skip/love/driver/report | this spec | Yes |
| Friendly neighbourhood names | this spec (display map) + SPEC-08 lists | Yes |
| One Ask control; composer inset | SPEC-25 placement + this spec | Yes |
| Schedule issues name stop + action | SPEC-29/35 + this spec | Yes, client copy/navigation |
| Hotel dates beside times | SPEC-10 display + this spec | Yes |
| Swap comparison deltas | UX_BACKLOG P2 + SPEC-17; money needs SPEC-23 | Partial: readable names and unknown-vs-known now; numeric cost only when SPEC-23 claims exist |
| Corridor transfer honesty | SPEC-36 (already refuses synthetic transfers) | Copy/IA only; do not invent mode/time |
| Driver-card language/source cues | SPEC-12 remainder | Yes, thin |
| Traveller vs diagnostics sync copy | SPEC-02 / Sync Status | Yes on trip chrome; keep debug screen |
| Account/sign-out/export/delete/RLS | SPEC-43, SPEC-24, SPEC-27 | **No. G1 blocker. Not visual polish.** |
| Actionable empty days / Add/Move | SPEC-42 + later Add/Move | **No until G0 reliability and Add/Move land.** |
| GPS "I am standing here" nearby | SPEC-34 (no GPS), SPEC-18, SPEC-25 remainder | **No GPS in this slice.** Trip-city / current stop coords only |
| Push notifications | SPEC-27, SPEC-35 | No |
| PDF/OCR/screenshot import | SPEC-39 deferred; SPEC-10 paste remainder | No |
| Durable preference form | SPEC-11 | No. Forced choice, not a settings dump |
| Group vote/split | UX_BACKLOG P3 | No |
| Full Offline Vault | SPEC-04 | No. Hotel Rescue already rejected as a duplicate shortcut |

## Design decisions

### 1. Reliability before chrome, chrome before destinations

G0 field-test blockers (corridor day fill, booking city ownership,
false hotel-return banners, typed swap candidates) land and get a
phone retest **before** this spec. SPEC-43 still gates the first
non-owner APK. Extra cities and a generic AI generator stay out.

The review's 1-10 build order is **not** the project order. It
optimizes product feel. This repo sequences by who may hold the APK
(`docs/RELEASE_READINESS.md`).

### 2. Home: featured trip first when one exists

When `featured_trip` is present, it is the first major block after
the greeting. Create-trip and corridor create sit below it, or in a
secondary control. Empty-state users still see Create first
(SPEC-26 decision 4).

Greeting is time-aware and uses data already on the snapshot:
destination display name, Now vs Up next, cache age when
`fromCache`. Do not invent "You're in Luang Prabang" from device
GPS.

Do not auto-redirect `/` to the itinerary (SPEC-38 decision 1).

### 3. One primary card action: open details

The whole activity card is tappable and opens place details.

At most one prominent inline action on a future flexible stop:
**Swap**. Skip/cancel, love, driver card, report, edit/delete live
in a labelled overflow and/or the details screen.

Touch targets for those actions are at least 44dp. Do not keep
36-pixel icon clusters competing with the title.

Venue title gets width: wrap at most two lines, then truncate.
Slot labels must not wrap (`Afternoon` on one line, or a shorter
token). Show at most two vibe chips; the rest behind More or
details.

`[BOOKING: HOTEL]` is internal. Render a small `Hotel` / `Flight` /
`Train` / `Tour` badge. Preserve Now / locked / completed / skipped
states with more than colour.

### 4. Never show raw slugs

`micro_location` values such as `nam_phou_fountain` are storage
keys (SPEC-08 closed lists). The itinerary shows a friendly label
(`Nam Phou fountain`) or omits the field. Same for booking type
enums.

Missing display name: omit or use a city-level fallback
(`Central Vientiane`), never the snake_case key.

### 5. One Ask entry on the itinerary

Remove the overlapping floating chat button **or** the persistent
bar, not both kept. Default: keep the bottom composer, drop the
FAB.

List bottom padding equals composer + nav bar + system safe inset
so Dinner and its actions are fully tappable.

Offline: the composer states that live Ask needs a connection
before send, and still does not queue a structural replan.

Suggested chips ("What should I do now?") may post existing
`ask_info` with a canned prompt. They must not become a second
mutation path. Production LLM on personal trip objects remains
SPEC-43-gated.

### 6. Warnings name the stop and a next action

`N schedule issues` expands to: venue, local date, reason, and one
honest action (open that card, swap if unlocked, or dismiss). Do
not invent a fix. Dismiss remains. Tapping an issue focuses that
node (SPEC-38).

Offline banner includes last successful save/sync in
traveller-friendly language when the timestamp exists. Do not show
`Inflight` / `Failed (permanent)` / raw UTC on the trip screen.
Those stay on Sync Status.

### 7. Hotel times include destination-local dates

Check-in and check-out show date and time, e.g. `Fri 2 Oct, 12:00`.
The nights/checkout summary may remain. If the same hotel node is
shown on later coverage dates, later cards are a continuation:
times stay, do not repeat Edit/Delete on every night if one
primary card already has them.

Checkout formula unchanged: `scheduled_start + duration_minutes`.
Coverage `[check-in local, checkout local)`. No `trip_stay`.

### 8. Swap is still confirm-before-mutate

Readable neighbourhood, slot fit, and hours when known. Missing
walking/cost/climate is labelled unknown. Do not fabricate
`INR 800` or minutes.

Before richer SPEC-17 envelopes exist, helpful copy comes from a
closed deterministic reason registry, not generated prose:

- `Fits this lunch slot`
- `Open during the planned time`
- `Keeps your next locked booking reachable`
- `In the same neighbourhood`
- `Matches your culture interest`

Only show a reason when the exact predicate used to accept/rank that
candidate is true. Show useful absence explicitly: `Price unknown`,
`live crowds unknown`, `traffic not checked`. SPEC-46 owns the shared
reason-code and temporary-context contract.

A second step may compare original vs candidate before confirm
(UX_BACKLOG P2). Selecting a row still does not apply. Sponsored
stays disclosed (SPEC-17 decision 15). Infrastructure and
slot-type filtering belong to the G0 field-fix, not this spec.

### 9. Corridor dates are unambiguous; transfers stay honest

Corridor form and city headers use `Fri, 2 Oct` style, not
`2/10/2026`. Days vs nights: say calendar days the form already
computes; do not invent nights.

Inter-city movement may appear as a **transfer needed** row
between segments. SPEC-36 still forbids synthetic mode, duration,
or booking. Unknown is valid copy.

### 10. Place details are operational, not a hero poster

Card tap opens `activity_detail` (wire it). Layout uses sourced
fields only:

- name, neighbourhood display label, category, typical dwell
- why-this-stop only from deterministic constraints already on
  the node (slot, hours, party tags). No unsourced "Travel Buddy
  chose this because..."
- open/closed only from structured hours + destination-local now
- walking from previous/next only from the same transit helper
  pack/swap use; else unknown
- driver card, Open in Maps, Swap, Skip, Love
- last-checked / provenance when SPEC-17 envelopes exist; else
  omit rather than fake a date

Placeholder hero images stay placeholders until sourced photos
exist. Do not scrape unlicensed galleries.

### 11. Map shell is deferred, not denied

A Timeline/Map switch is the right long-term IA (UX_BACKLOG P1).
This slice may add a **non-interactive** "Map coming soon" route
only if it does not steal G0/G1 time. Cached map images still need
tiles, storage, and licence. Full offline maps remain P3.

Do not request background GPS (UX_BACKLOG section 0).

### 12. Empty days stay honest until Add/Move exists

SPEC-42 empty days with Add activity are the long-term product.
Until that command exists, G0 may pack every requested corridor
day so LP 7-9 Oct are not dead. This spec must not ship "Add
activity / Copy previous day / Suggest a low-effort plan" buttons
that post nothing or that invent a local replan.

Copy previous day is rejected until a server command exists:
duplication vs hours, unique venue_id, and locked anchors.

## Red flags (shouted)

1. **Review build order vs G1.** Putting account lifecycle at step 6
   after nearby discovery would ship personal trip data to another
   person on a self-issued UUID. That order is unsafe.
   `RELEASE_READINESS.md` G1 still requires SPEC-43 first.

2. **Invented money and walking in mockups.** The sample
   `- INR 800` / `+ 12 min` is a trust defect if rendered without
   SPEC-23 claims and deterministic transit. Show unknown.

3. **"Why Travel Buddy chose it" as marketing copy.** Generated
   rationale without a SPEC-17 envelope becomes fake provenance.

4. **Device GPS "what now?"** SPEC-34 explicitly left GPS out.
   Live location needs permission, battery, and privacy consent
   (SPEC-43). Trip-city search is the allowed near-me until then.

5. **Map-first as the next cycle.** A real map is a product, not a
   CSS change. It has already been parked behind reliability
   (UX_BACKLOG section 2). Reopening it now delays the Oct 2 trip.

6. **Actionable empty days without Add/Move.** Buttons on "Open
   day" that cannot mutate are worse than blank days. Sequencing:
   G0 pack-or-reason, then Add/Move, then SPEC-42 empty-day IA.

7. **PDF/OCR/screenshots.** New PII intake and likely model
   egress. SPEC-39 stays deferred. SPEC-10 paste remainder only.

8. **Persistent preference checkboxes.** Conflicts with SPEC-11
   (forced choice, revealed preference). A settings dump is the
   failure mode that spec exists to avoid.

9. **Copy-previous-day / keep-day-open plus auto-suggest.** Easy
   to violate unique venues and hours. Server command or nothing.

10. **Two reviews in one note.** "Do not re-architect" and "map
    command center + rewritten cards + nearby GPS" fight each
    other. This spec takes the friction fixes and defers the
    shell rewrite.

## Tests (when implemented)

- Home with `featured_trip`: that card appears above Create.
- Activity card: tap opens details; Swap remains; skip/love/driver
  are not a four-icon row on the title.
- `nam_phou_fountain` does not appear as user-visible text.
- `[BOOKING:` does not appear.
- One Ask control; last node fully visible above composer (widget
  padding assertion).
- Hotel card includes a month-day on check-in and check-out.
- Schedule issue row includes a venue name and opens focus.
- Offline banner includes a relative or local last-saved phrase
  when `cachedAt` exists.
- Swap confirm still requires an explicit confirm control.

Flutter UNVERIFIED on Databricks. R1 after Dart writes.

## Acceptance

A phone-width itinerary:

- readable titles and neighbourhoods, no snake_case IDs
- details without guessing which 36px icon to hit
- one Ask control; no stop hidden behind chrome
- swap still confirm-before-mutate; missing deltas say unknown
- schedule issues name affected stops
- offline copy includes recency when known
- hotel stays show local dates and times
- corridor dates unambiguous; no invented transfer facts
- 44dp minimum on remaining icon actions

## Non-goals

- Merge, deploy, APK, G0 pass claims
- SPEC-43 implementation
- New cities, LLM itinerary generator, LangGraph
- Geocoder, `trip_stay`, naive UTC wall-time reopen
- Optimistic offline replan
- RevenueCat / real IAP (placeholder upgrade stays until billing)
- Design-token fashion pass (UX_BACKLOG P4)
