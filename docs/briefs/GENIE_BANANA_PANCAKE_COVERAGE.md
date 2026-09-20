# Genie Brief: Measure Banana Pancake Town Coverage

> Status: READY. Research/data-only task. This does not onboard a city.
>
> This task may run before SPEC-13 and SPEC-20. It writes measurement code,
> reproducible results, and documentation only. It must not write venue seed
> files, call the venue loader, alter Supabase, or change runtime region lists.

## Read first

- `docs/WAYS_OF_WORKING.md`
- `docs/ENGINEERING_RULES.md`
- `docs/CORRIDOR_COVERAGE.md`
- `docs/MARKET_STRATEGY.md` (Sep 2026 addendum)
- `data/corridor_coverage.json`
- `docs/specs/SPEC-13-region-locale-registry.md`
- `docs/specs/SPEC-20-city-onboarding-kit.md`

The existing measurement definition is authoritative. Stop and report any
contradiction before changing it. Do not edit this brief.

## Goal

Make the Aug 2026 OpenStreetMap coverage measurement reproducible, then measure
the five unmeasured Banana Pancake towns that affect the recorded sequence:

1. Chiang Mai
2. Pai
3. Siem Reap
4. Phnom Penh
5. Hoi An

The result informs sequencing and curation effort. It is not an onboarding
approval and must not reorder the strategy automatically.

## Preflight and branch

1. `git fetch origin`
2. Start from clean, current `origin/main`.
3. Confirm the two existing sources agree for all ten measured cities:
   `docs/CORRIDOR_COVERAGE.md` and `data/corridor_coverage.json`.
4. Create `data/banana-pancake-coverage`.
5. Use public Overpass endpoints only. Do not use Google Places, TripAdvisor,
   commercial-app scraping, or a personal API key.

## Required implementation

### A. Add a reproducible measurement script

Add `scripts/measure_corridor_coverage.py`.

The script must:

- read city definitions from a checked-in JSON input, not a Python dictionary;
- query OSM nodes, ways, and relations carrying `tourism`, `historic`, or
  `amenity` in `restaurant|cafe|bar|marketplace`;
- use Overpass QL:

```text
[out:json][timeout:90];
(
  nwr["tourism"](S,W,N,E);
  nwr["historic"](S,W,N,E);
  nwr["amenity"~"^(restaurant|cafe|bar|marketplace)$"](S,W,N,E);
);
out tags;
```

- count `pois`, `named`, `name_en`, `name_local_tag`,
  `local_script_in_name`, `bridgeable`, and `wikidata`;
- preserve the exact existing definition of `bridgeable`;
- support Thai and Khmer script detection by Unicode ranges;
- treat Vietnamese as a Latin-script language using explicit language tags,
  consistent with the existing Hanoi / Da Nang / HCMC rows;
- sleep at least five seconds between requests;
- retry HTTP 429 and 5xx with bounded exponential backoff and a descriptive
  user agent;
- write JSON deterministically (stable city order, two-space indentation,
  final newline);
- offer `--city`, `--input`, `--output`, and `--endpoint` arguments;
- refuse to overwrite the canonical result after a partial failure;
- have a fixture/offline mode so tests never call Overpass.

Do not make import-time network calls.

### B. Add candidate measurement boxes

Add a focused checked-in input such as
`data/banana_pancake_coverage_targets.json`. For each town record:

- city and country code;
- `local_lang`;
- script family;
- `[south, west, north, east]` bounding box;
- a short `bbox_basis` explaining what the box is intended to cover.

Boxes are measurement decisions, not city boundaries. Draw them around the
traveller-relevant urban core. Before querying, print each box and inspect it
on an open map. Record corrections in the commit rather than silently widening
a box until the count looks good.

Use these as reviewable starting boxes, not unquestionable truth:

| Town | Starting box `[S,W,N,E]` | Language / script |
|------|---------------------------|-------------------|
| Chiang Mai | `[18.73,98.91,18.84,99.03]` | th / Thai |
| Pai | `[19.33,98.40,19.39,98.47]` | th / Thai |
| Siem Reap | `[13.32,103.82,13.41,103.91]` | km / Khmer |
| Phnom Penh | `[11.50,104.84,11.62,104.96]` | km / Khmer |
| Hoi An | `[15.84,108.27,15.93,108.36]` | vi / Latin |

If visual inspection changes a box, explain why in the result commit.

### C. Preserve and extend the canonical data

Do not replace the existing ten rows with fresh values silently. Overpass is a
live database and counts drift.

Preferred output:

- keep `data/corridor_coverage.json` as the canonical dated snapshot;
- append the five new city rows;
- update `measured_at` only if all fifteen cities are re-run in one complete
  pass; otherwise add a per-row `measured_at` to new rows and preserve the
  original top-level date semantics;
- record endpoint and script version / git SHA;
- update `docs/CORRIDOR_COVERAGE.md` with the five measured rows and any
  methodology clarification needed for Khmer.

If the current schema cannot represent mixed measurement dates honestly,
make the smallest backwards-compatible schema extension and test it.

### D. Tests

Add focused tests using saved miniature Overpass responses. Prove:

1. node, way, and relation elements are all counted;
2. Thai and Khmer text in plain `name` is detected as local script;
3. `name:th` / `name:km` plus matchable English is bridgeable;
4. Vietnamese Latin-script handling matches the existing definition;
5. no name is not named or bridgeable;
6. `wikidata` counts once per OSM element;
7. retry is bounded;
8. a partial run does not overwrite the canonical output;
9. output order and formatting are deterministic;
10. tests make zero network calls.

## Interpretation rules

- High `bridgeable` means sourced identity is available; it does not mean
  opening hours, price, accessibility, or vibe are complete.
- Raw POI count must not decide priority. Pai may remain Phase A because route
  adjacency and backpacker density matter even if its bridgeable count is low.
- A low count must not trigger model-generated local names.
- No city is approved for load by this task.
- Do not compare boxes as if they were equal-area city boundaries.

## Acceptance

- [ ] One reusable script, no import-time network
- [ ] Five reviewed target definitions in data
- [ ] Offline fixture tests for counting and failure behavior
- [ ] Five dated measurements in the canonical snapshot
- [ ] `docs/CORRIDOR_COVERAGE.md` updated without overwriting historical counts
- [ ] No venue JSON, migration, Supabase, Flutter, runtime registry, or loader
      changes
- [ ] `git diff --check`
- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] focused tests and full `pytest -q -ra`, with skip reasons named (R8)
- [ ] verify from the reviewed commit / `origin/main` as required by R10

## Handoff

Report:

- branch and SHA;
- endpoint and UTC measurement time;
- final bounding boxes and any changes from the starting boxes;
- the five result rows;
- retries or partial failures;
- exact tests run;
- explicit confirmation that no city was onboarded.

Do not say a town is "ready" from these counts. Recommend whether the measured
identity layer is sufficient for a 40-to-60-anchor SPEC-20 candidate pull, with
confidence and caveats.
