# Genie Brief: SPEC-40 Guided Create Trip Foundation

## Read first

- `docs/WAYS_OF_WORKING.md`
- `docs/ENGINEERING_RULES.md`
- `docs/specs/SPEC-40-guided-create-trip.md`
- `docs/specs/SPEC-03-party-context.md`
- `docs/specs/SPEC-11-forced-choice-preferences.md`
- `docs/specs/SPEC-32-real-laos-trip-creation.md`
- `docs/specs/SPEC-36-laos-corridor-trip.md`
- `docs/specs/SPEC-38-active-trip-mode.md`

The SPEC-40 spec is authoritative. Stop and report any contradiction before
coding. Do not edit this brief.

## Goal

Build the first guided Create Trip vertical slice:

1. destination;
2. inclusive start/end dates;
3. party;
4. zero-to-three trip interests;
5. review and deterministic catalog create.

This brief does not implement LLM generation, similar-trip retrieval, memory,
or PDF intake.

## Preflight and branch

1. `git fetch origin`
2. Start from clean, current `origin/main`.
3. Confirm main contains:
   - PR #59 / `fefc4ec`;
   - the SPEC-38 field-pass documentation;
   - `docs/specs/SPEC-40-guided-create-trip.md`;
   - this brief.
4. Create `feat/spec40-guided-create`.
5. Read current code before editing. Do not reconstruct files from this brief.

## Required implementation

### A. One server registry

Add a focused server registry for:

- party option IDs and labels, using the existing SPEC-03 vocabulary;
- interest IDs, labels, category matches, and vibe-tag matches;
- the product ceiling of five single-city range days.

Validation, ranking, and the options response must use this registry. Flutter
must consume advertised IDs/labels rather than mirror the vocabulary.

### B. Typed create contract

In `models/schemas.py`:

- add optional inclusive `end_date` to `CreateTripRequest`;
- type the accepted `interest_ids`;
- add typed creation context to `TripState` for destination, requested local
  dates, and interest IDs;
- preserve parsing of all existing stored trips.

Reuse `TripPartyIn`; do not create another party model or table.

### C. Advertise viable options

Keep existing `supported_regions` and `supported_corridors` response fields.
Add `create_trip_options` to GET `/api/v1/trips` with:

- server-owned party options;
- server-owned interest options;
- `max_days_by_region`.

For each region:

```text
max_days = min(5, floor(unique eligible stable venue IDs / 4))
```

Do not advertise a region max unless the range builder can actually fulfill
it. Old API clients and old cached Home snapshots must remain compatible.

### D. Atomic deterministic range builder

Keep legacy create without `end_date` exactly compatible with SPEC-32.

For requests with `end_date`:

- validate inclusive destination-local dates;
- reject reversed, past, unknown, and above-advertised ranges with a typed 422;
- select exactly four unique venues per day;
- never repeat a venue anywhere in the trip;
- apply the registry's interest category/tag score;
- preserve category diversity;
- break ties by normalized venue name then stable venue ID;
- schedule each day from 09:00 in the region IANA timezone and store UTC;
- build and validate all days before `save_trip` or `save_trip_party`;
- save once only after the complete build succeeds.

No LLM, embeddings, hybrid search, external provider, or reroute quota may be
used.

### E. Persist and return creation inputs

- Persist creation context inside trip state JSON.
- Continue persisting party through existing SPEC-03 methods.
- GET `/trip/{id}` must return party and creation context.
- Both database implementations must remain compatible. No migration is
  expected; stop and explain before adding one.
- Never collect a child name or birth date.

### F. Flutter models and repository

Update Dart models for:

- advertised create options;
- party input/response;
- creation context;
- backward-compatible old cached JSON.

Replace the repository's single-date create call with a typed range create
method that sends destination, start/end, party, and interest IDs. Keep a
compatibility path where current tests or callers still require legacy create.
Do not change corridor request shape.

### G. Full-screen wizard

- Add route `/trip/create`.
- Home's large Create card opens that route.
- Keep the corridor card and `CorridorDateForm` separate.
- Build five easy, scroll-safe steps: destination, dates, party, interests,
  review.
- Back preserves entered values.
- Use a date-range picker and the server-advertised regional max.
- Party supports solo, couple, friends, family-young-kids, family-teens, and
  multi-generation. Use age bands only when needed.
- Interests allow zero to three; zero means balanced.
- Review shows exact destination, dates, party, and interests.
- Disable repeated submit while in flight.
- Typed failure keeps wizard state. Success opens the fetched itinerary.
- No overflow at 800x600; controls remain reachable with large text.

Use existing theme/type/spacing tokens. Do not redesign unrelated Home or
itinerary surfaces.

## Required backend tests

Add focused tests proving:

1. omitted `end_date` preserves the legacy venue sequence;
2. a valid four-day range yields 16 nodes on four local dates;
3. no repeated venue IDs;
4. deterministic repeat;
5. selected interests alter priority through the registry;
6. invalid interest, reversed date, past date, and over-cap each return the
   correct typed 422;
7. capacity failure leaves no trip or party;
8. party and creation context round-trip through GET trip;
9. no LLM/hybrid/quota call;
10. corridor create stays compatible;
11. options tests fail if the list is empty or validation drifts.

Sabotage the implementation behind the important guards and confirm those
tests fail before restoring it.

## Required Flutter tests

Prove:

1. old/new option JSON and cached Home snapshots parse;
2. Home Create opens the wizard while corridor entry remains unchanged;
3. every step and Back preserves state;
4. date validation uses the advertised region max;
5. zero interests works and a fourth is refused;
6. repository payload has exact dates, party, and interest IDs;
7. double submit produces one request;
8. server failure preserves entries;
9. success opens the returned trip;
10. 800x600 and large-text layouts remain scroll-reachable.

Use production widgets and typed production exceptions. Do not replace
behavioral assertions with source-text assertions.

## Gates

Run and report:

```text
pytest -q -ra
ruff check . --config pyproject.toml
ruff format --check .
cd mobile
flutter analyze --no-fatal-infos
flutter test
flutter build apk --debug --dart-define=TB_API_BASE_URL=https://example.invalid
```

Also run repository R1/R14 guards after Dart writes. Report pass, fail, skip,
and expected skip reasons separately.

## Delivery

1. Review the full diff against `origin/main`.
2. Update current docs only where implementation status changed.
3. Commit and push `feat/spec40-guided-create`.
4. Open a PR to `main`.
5. Return:
   - PR URL;
   - head SHA;
   - changed-file summary;
   - exact test counts and skips;
   - sabotage proofs performed;
   - remaining risks.
6. Do not merge, deploy, build a signed APK, or instruct phone testing. Stop
   for planning-agent review.
