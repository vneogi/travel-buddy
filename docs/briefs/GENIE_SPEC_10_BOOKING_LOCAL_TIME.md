# Genie Brief: SPEC-10 booking wall times are destination-local

Start a new branch from current `origin/main` (must include `e7a0457` /
`613b10f` or later):

```text
feat/spec10-booking-local-time
```

Do not merge. Do not deploy. Do not build an APK.
Do not touch `feat/spec25-grounded-ask`.
Do not implement named itinerary slots, `pack_day` booking wiring,
destination date-cap removal, place-detail cards, or paste/parser work.

Read first:

- `docs/specs/SPEC-10-booking-anchors.md` (Remainder: stay interval
  semantics and post-arrival intent)
- `docs/AWAITING_VERIFICATION.md` (Sep 18 2026 old-APK hotel finding)
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`
- `services/destination_tz.py`
- `agents/state_machine.py` (`ADD_BOOKING` / `EDIT_BOOKING` start parse)
- `mobile/lib/features/booking/add_booking_sheet.dart`
- `mobile/lib/core/destination_tz.dart`
- `mobile/lib/widgets/activity_card.dart` (`formatDestinationTime`)

Do not edit this brief.

## Why this slice exists

Sep 18 old-APK evidence: owner entered hotel check-in Oct 2 18:02 and
check-out Oct 3 15:00. The itinerary showed a single Oct 3 01:02 hotel
card. That is a seven-hour shift, matching Asia/Vientiane.

Current code explains it without guessing:

1. Flutter `AddBookingSheet` sends
   `_scheduledStart.toIso8601String()` (`add_booking_sheet.dart`).
   A non-UTC Dart `DateTime` emits a naive ISO string (no `Z`, no offset).
2. `state_machine.py` does `fromisoformat`, then if `tzinfo is None`
   stamps `replace(tzinfo=timezone.utc)`.
3. The card formats with `formatDestinationTime` in the node `geoRegion`
   (`UTC+7` for Laos). `18:02Z` becomes Oct 3 01:02 local.

The hotel then appears on the wrong local date because coverage is derived
from that shifted `scheduled_start`.

This is a booking correctness blocker for the next APK. Reproduce on
current `main` with a failing test, then fix. Do not wait for the Windows
laptop to write the Python proof.

## Goal

After this slice:

- a traveller-entered destination-local civil time round-trips as that
  same local time on the itinerary card;
- naive booking ISO strings mean destination-local wall time for the
  trip/node `geo_region`, not UTC;
- an already-offset or `Z` timestamp is that instant, converted to UTC
  once;
- `edit_booking` uses the same parser as `add_booking`;
- Flutter does not use device timezone as the hotel/flight wall clock
  when the trip has a known region;
- hotels still have no new `trip_stay` table; check-out remains
  `scheduled_start + duration_minutes` on the wire for this slice;
- both endpoints still display (check-in local and implied check-out
  local) so a stay is not a single mysterious 01:02 stamp.

## Explicitly out

- Named slots (morning/lunch/afternoon/dinner) and travel-day remaining
  slot packing (SPEC-41 remainder; specified, not this branch).
- `pack_day` consuming bookings.
- Catalog-derived `max_days` UI removal (SPEC-42).
- Place-detail / insider-tip cards.
- Agoda/PDF parser corpus, SPEC-39, forwarding mailbox.
- SPEC-25 merge, LangGraph, MCP, deploy, APK.
- New check-in/check-out columns or `trip_stay`.
- Changing activity create/swap times that are already stored as UTC
  instants from the catalog packer.

## 1. One conversion helper

Add a public helper next to `to_destination_local` in
`services/destination_tz.py` (name may vary; one function, one contract):

```text
parse_destination_wall_time(raw, geo_region) -> datetime UTC
```

Rules:

- `raw` is `str` or `datetime`.
- Naive `datetime` or naive ISO (`2026-10-02T18:02:00`) attaches
  `destination_tz(geo_region)` then `astimezone(UTC)`.
  Never `replace(tzinfo=timezone.utc)` on a booking wall time.
- Aware values (`Z` or numeric offset) convert once with
  `astimezone(UTC)`.
- Unknown region: fail closed with a typed error the event path can
  surface; do not silently assume UTC for bookings. Catalog/packer UTC
  instants are not this helper's job.
- Use `astimezone`. Do not `replace(tzinfo=...)` on an aware value.

`ADD_BOOKING` and `EDIT_BOOKING` must call this helper. Do not copy the
parse into both branches.

Region for the parse: `prefs.geo_region` if present, else
`trip_state.geo_region`. A Vientiane trip must not parse a hotel using
the server clock timezone.

## 2. Flutter wire contract

Keep `scheduled_start` as one ISO string plus `duration_minutes`.

Required:

- The date/time pickers for bookings represent destination-local civil
  time using `destinationOffset(geoRegion)` / existing destination TZ
  helpers, not `DateTime.now()` device local, when the trip region is
  known.
- The payload must not rely on "naive ISO means UTC". Either:
  - send naive ISO and document that the server attaches destination TZ
    (matches section 1), or
  - send an offset ISO built from destination offset, not device offset.
  Pick one and test it. Do not send device-local naive strings.

If the Dart SDK is unavailable in the execution environment, still change
the Python contract and add a focused Dart test under
`mobile/test/` that encodes the chosen payload. Mark Flutter analyze /
widget tests UNVERIFIED rather than claiming they passed.

Display already uses `formatDestinationTime`. After the server stores the
correct UTC instant, Oct 2 18:02 local must render `18:02` on the card,
not `01:02`. If the card still shows a single timestamp for a hotel,
show check-in and check-out local times derived from start plus duration
on that same card. No schema change.

## 3. Tests (R17)

Python, via TestClient `add_booking` / `edit_booking` on a Vientiane trip,
not helper-only tests.

Must fail on current `main` before the fix, then pass:

1. POST naive `scheduled_start=2026-10-02T18:02:00` with
   `geo_region=vientiane_laos`, duration covering checkout Oct 3 15:00
   local. Response node, converted with `to_destination_local`, is
   2026-10-02 18:02 in `Asia/Vientiane`. It is not 2026-10-03 01:02.
2. Sabotage: restore `replace(tzinfo=timezone.utc)` on naive booking
   parse; test 1 goes red. Restore the helper. Name the test in the PR.
3. Aware `2026-10-02T18:02:00+07:00` stores the same UTC instant as
   naive 18:02 for that region.
4. `Z` timestamp `2026-10-02T11:02:00Z` is 18:02 local, not 11:02 local.
5. `edit_booking` naive start uses the same helper; no UTC stamp.
6. Hotel coverage local dates include Oct 2 and exclude the checkout
   local date (existing `[check_in, checkout)` rule) for that fixture.

Do not assert `len(nodes) >= 1` as the only check. Assert local hour,
local date, and UTC instant.

Optional Dart unit test: naive or offset payload from the sheet constructor
matches the chosen contract; destination formatter of the stored UTC
instant is `18:02`.

## 4. Gates

```text
pytest -q tests/test_spec10_booking_local_time.py
pytest -q tests/test_spec10_flight_hotel_anchors.py
pytest -q tests/test_booking_anchors.py
pytest -q
ruff check .
ruff format --check .
git diff --check
```

If Flutter SDK is present:

```text
dart format --output=none --set-exit-if-changed mobile/lib mobile/test
flutter analyze --no-fatal-infos
flutter test mobile/test/features/booking/
```

If Flutter SDK is absent, say so. Do not invent a pass.

## Done when

- The naive Laos 18:02 fixture round-trips to 18:02 local.
- Naive-as-UTC sabotage is named and red then restored.
- add and edit share one helper.
- Flutter payload/picker does not use device TZ for a known region, or
  the Dart gap is explicitly UNVERIFIED for laptop.
- PR opened. No merge, no deploy, no APK.

## Commit style

ASCII in `.py` comments/docstrings (R14). LLM never mutates without HITL.
Do not quote walking minutes in user-facing strings.
