# Genie Brief: Phase A Chiang Mai and Pai Extension

> Status: DRAFT / BLOCKED. Do not implement yet.
>
> Unblock only after SPEC-13 and SPEC-20 are implemented and verified from
> `origin/main`, SPEC-17 can store the required claim provenance, the ODbL
> consuming-side decision is recorded, and the applicable G1 gate in
> `docs/RELEASE_READINESS.md` is closed before non-owner distribution.
>
> This is the future execution contract requested by the Sep 2026 Banana
> Pancake sequencing decision. It records scope now so Phase A is not rebuilt
> from chat later. It is not permission to hand-load Thai venue JSON.

## Read first

- `docs/WAYS_OF_WORKING.md`
- `docs/ENGINEERING_RULES.md`
- `docs/MARKET_STRATEGY.md` (Sep 2026 addendum)
- `docs/RELEASE_READINESS.md`
- `docs/CORRIDOR_COVERAGE.md`
- `docs/specs/SPEC-13-region-locale-registry.md`
- `docs/specs/SPEC-17-trust-and-verification.md`
- `docs/specs/SPEC-20-city-onboarding-kit.md`
- `docs/specs/SPEC-21-osm-upstream-contribution.md`
- `docs/specs/SPEC-36-laos-corridor-trip.md`
- `docs/briefs/GENIE_BANANA_PANCAKE_COVERAGE.md`

The specs and strategy are authoritative. Stop and report contradictions
before coding. Do not edit this brief.

## Goal

Extend the existing Laos backpacker field graph into northern Thailand:

1. onboard a sourced 40-to-60-anchor Chiang Mai spine through the completed
   SPEC-20 pipeline;
2. onboard Pai only after Chiang Mai passes the city gate;
3. advertise one bounded, deterministic north-Thailand-to-Laos route using
   those registered regions;
4. preserve local time, native-script identity, provenance, offline behavior,
   and the existing Laos itinerary contracts.

This slice proves repeatable city onboarding and route adjacency. It does not
claim complete Thailand coverage.

## Blocking preflight

Stop without creating a branch unless all are true:

1. `origin/main` contains a verified SPEC-13 region registry with cached client
   consumption and foreign-key enforcement.
2. `origin/main` contains the SPEC-20 candidate puller, refusal gate, existing
   loader output, and Bangkok end-to-end acceptance case. Chiang Mai/Pai
   ingest does not skip that proof.
3. SPEC-17's claim model can store generated subjective fields without writing
   them as sourced identity facts.
4. The ODbL analysis in SPEC-21 / PROJECT_STATUS has a recorded owner decision
   for the consuming database and attribution.
5. The coverage task has measured Chiang Mai and Pai with dated boxes.
6. The current working tree is clean and current `origin/main` passes its
   documented gates.
7. If any non-owner will receive the build, G1 in
   `docs/RELEASE_READINESS.md` is closed. A hostel QR is non-owner
   distribution.

Record the satisfying commit or dated evidence for each item in the PR. "The
code appears to exist" is not a preflight pass.

After preflight, create `feat/phase-a-chiang-mai-pai` from current
`origin/main`.

## Scope boundaries

In scope:

- Chiang Mai region row and sourced anchor spine;
- Pai region row and sourced anchor spine;
- one route/corridor definition joining the Thai towns to the existing
  Luang Prabang side of the field graph;
- server create/options and Flutter selection/rendering needed for that route;
- Thai native-name driver-card behavior through existing generic contracts;
- deterministic tests and documented curation effort.

Out of scope:

- Bangkok onboarding (SPEC-20 acceptance case, not this Phase A);
- southern Thailand or islands;
- Ha Giang, Vietnam, Cambodia, Malaysia, Singapore, Bali;
- transport booking, border/visa promises, or live bus/boat inventory;
- asserting a slow-boat timetable as a durable fact;
- model-generated identity, local names, opening hours, prices, accessibility,
  safety, or dietary claims;
- a general arbitrary route builder;
- new recommendation models, learned ranking, or cross-user personalization;
- production marketing or hostel QR rollout.

## Required implementation

### A. Registry rows, no runtime exceptions

Use the implemented SPEC-13 registry and its existing migration / seed
mechanism. Do not add another city dictionary.

Each row must provide and validate at least:

- stable `region_key`;
- city and country;
- IANA timezone `Asia/Bangkok`;
- currency `THB` and the registry's minor-unit convention;
- ordered languages with Thai first;
- Thai primary script;
- reviewed measurement / ingestion bounding box;
- fare and payment fields only where the registry allows sourced or explicitly
  unknown values.

Pai's modeling choice must be explicit:

- preferred: its own registered region, because timezone is shared but
  bounding box, venue pool, itinerary dates, and route segment differ;
- if the accepted SPEC-13 implementation has a first-class parent/satellite
  relationship, use it;
- do not hide Pai inside `chiang_mai_thailand` by a larger bounding box.

Unknown facts remain null / named unavailable. Do not copy Bangkok defaults.

### B. Source candidate identity through SPEC-20

Run the implemented candidate puller for Chiang Mai. Produce a 40-to-60-anchor
spine that covers the traveller-relevant urban core, then pass `validate_city`
without waivers added merely to make this city pass.

Required identity for every accepted anchor:

- source and source URL / external identifier;
- English matchable name;
- Thai name when the source supplies one;
- coordinates inside the registered box;
- category from the canonical taxonomy.

Then repeat for Pai. Do not start Pai curation until Chiang Mai's gate and
loader dry run pass.

The model may propose subjective fields only through the SPEC-17 claim path.
Generated Thai names are forbidden. Missing Thai is preferable to invented
Thai.

Record:

- candidate count;
- accepted anchor count;
- rejection counts by reason;
- manual-review count;
- sourced vs generated fields;
- elapsed curator time.

These are onboarding evidence, not permanent test-count claims.

### C. Route contract

Add one server-owned route/corridor definition using registered region keys.
Its product sequence is:

```text
Chiang Mai -> Pai -> Chiang Mai / north-Thailand transfer -> Luang Prabang
```

The exact transport representation must follow the corridor model that exists
when this brief unblocks. Do not fabricate Pai-to-Laos direct service if the
real route returns through Chiang Mai or travels via Chiang Khong / Huay Xai.

Requirements:

- city itinerary segments are deterministic and use each region's local date;
- no route definition duplicates timezone, language, currency, or bounding-box
  facts from the region registry;
- transport joins are informational unless backed by a sourced, fresh provider;
- border crossing, visa eligibility, departure times, and boat operation are
  never asserted from model memory;
- locked bookings stay immovable;
- sparse/empty-day behavior follows the then-current SPEC-42 contract;
- old Laos trips and old cached route payloads still parse.

If the existing corridor model cannot represent a transfer without lying, stop
and write the missing contract. Do not encode it as an activity venue.

### D. Flutter

Consume advertised regions and routes from the API. Do not mirror Thai city
IDs, labels, maximum spans, or language metadata in Dart.

Prove:

- Chiang Mai and Pai render from server options;
- destination-local dates remain Thai-local through create, cache, and render;
- Thai names reach the existing driver card offline where sourced;
- English fallback is explicit where Thai is absent;
- older cached Laos-only options still parse;
- empty and partially populated dates follow current SPEC-42 rendering;
- release endpoint remains HTTPS and identity-scoped cache behavior is
  preserved.

After any Dart write, run R1's escaped-interpolation grep.

### E. Tests

Tests must fail if:

1. either city bypasses the region registry;
2. coordinates fall outside the declared region;
3. Thai localized identity lacks provenance;
4. a generated Thai venue name is accepted as sourced identity;
5. an unknown taxonomy term reaches loader output;
6. Pai venues leak into Chiang Mai search or vice versa;
7. local 09:00 changes date after UTC serialization;
8. the route hardcodes region order separately from its registry;
9. a transport or border claim has no source/freshness;
10. an existing Laos corridor or cached payload stops parsing;
11. Flutter mirrors server-owned city IDs or span caps;
12. the driver-card fallback presents generated Thai as authoritative.

Use the actual production service and exception types (R3), both persistence
backends where persistence changes (R4), and one source of truth per registry
(R5).

## Release and data guard

Completing this code does not authorize public distribution.

- Owner-only testing remains G0.
- First hostel or external tester is G1 and needs the release ledger closed.
- No learned ranking starts from Phase A signals until SPEC-43 consent,
  ownership, deletion, and influence thresholds pass.
- OSM attribution and database obligations follow the recorded ODbL decision.
- Do not advertise "Thailand supported" from two northern towns.

## Acceptance

- [ ] Every blocking preflight item named with evidence
- [ ] Chiang Mai registry row and 40-to-60 sourced-anchor spine pass SPEC-20
- [ ] Pai registry row and 40-to-60 sourced-anchor spine pass SPEC-20, or the
      measured identity layer proves that target impossible and the owner
      explicitly accepts a smaller threshold
- [ ] No hand-maintained runtime city dictionary or Python exception
- [ ] No generated Thai identity accepted as sourced
- [ ] One honest route contract joins northern Thailand to the Laos graph
- [ ] Existing Laos behavior and stored payloads remain compatible
- [ ] API-driven Flutter options, local dates, offline driver card, empty days
- [ ] ODbL attribution / consuming-side decision implemented as recorded
- [ ] `git diff --check`
- [ ] backend lint / format and full tests pass with skips named
- [ ] Flutter analyze, tests, and R1 grep pass
- [ ] Hosted/API/APK verification is recorded in the correct ledgers only

## Handoff

Report:

- branch, SHA, and parent `origin/main`;
- evidence for every blocker;
- registry keys and final bounding boxes;
- candidate / accepted / rejected curation summary per city;
- all source and attribution changes;
- route shape and any deliberately unmodeled transfer facts;
- exact backend and Flutter gates run;
- what still requires hosted or device verification;
- explicit statement that no public or hostel distribution is authorized by
  the merge.
