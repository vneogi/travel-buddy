# Genie brief: Isochrones trial -- Haversine vs network reach

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

This brief runs **after** F2 and F3 are on main, and only when the
planning agent (or owner) sends it with a real base SHA. Do not start
it early.

## 0. Context

Decision record: `docs/decisions/NETWORK_REACHABILITY.md`. Owner
penciled Google Maps Platform Isochrones as an optional enrichment for
in-trip reachability. Before any product wire-up we need measured
disagreement between today's Haversine walk
(`services/transit.walking_minutes`) and a real network isochrone on
three catalogs the owner cares about: Stone Town, Nungwi, Luang Prabang.

This slice is a **trial harness only**: a script, recorded fixtures,
and tests that prove the comparison logic. It does not call Google from
CI. The owner runs one live command on Windows with their Maps key.

## 1. Goal

1. A script that, given a region, an origin venue (or lat/lng), a walk
   duration in minutes, and either a recorded GeoJSON fixture or a live
   flag, reports:
   - venues Haversine says are reachable in that duration;
   - venues whose coordinates fall inside the isochrone MultiPolygon;
   - the symmetric difference (Haversine-only, isochrone-only, both).
2. Recorded fixtures for three origins (one per region) at 15, 30, and
   45 minutes so CI stays offline and deterministic.
3. A short markdown report template the owner fills after the live run
   (counts only; no secret keys).
4. No product code path changes. No What Now / swap / packing changes.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief. Confirm F2 and F3 are on that main (Tanzania rule in
   `languagePriority`; F3 helper or picker present). If not, stop.
2. Confirm `docs/decisions/NETWORK_REACHABILITY.md` and this brief exist.
3. Confirm `scripts/isochrone_trial.py`,
   `tests/test_isochrone_trial.py`,
   `data/isochrone_fixtures/` (or the agreed path), and
   `origin/feat/isochrone-trial` do not exist.
4. Branch: `feat/isochrone-trial`.

## 3. Read before editing

- `docs/decisions/NETWORK_REACHABILITY.md`
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `services/transit.py` (`walking_minutes`, `haversine_km`)
- `services/google_maps_real.py` (how we already call Maps; pattern for
  key env `TB_GOOGLE_MAPS_API_KEY`, never log the key)
- Google Isochrones docs (generate method): origin lat/lng, travelMode
  `WALK`, travelDuration as `"Ns"`, travelDirection `FROM`, response
  `isochrone.geoJson` MultiPolygon. Point-in-polygon must respect
  exterior rings and holes (RFC 7946).
- Catalog loaders: how to list venues for `zanzibar_tanzania`,
  `nungwi_tanzania`, `luang_prabang_laos` from `data/*.json` offline.

## 4. Files you may touch

- `scripts/isochrone_trial.py` (new)
- `tests/test_isochrone_trial.py` (new)
- `data/isochrone_fixtures/` (new directory; ASCII GeoJSON fixtures + a
  tiny README listing origin coords and durations; no API keys)
- `docs/briefs/ISOCHRONE_TRIAL_OWNER_RUN.md` (new; owner runbook + empty
  results table)

Nothing else. No routers, no What Now, no Flutter, no requirements
change unless a pure stdlib/shapely-free point-in-polygon needs a tiny
helper in-tree (prefer a small winding-number implementation in the
script; do not add a geospatial dependency).

## 5. The change

### 5.1 Script CLI

```
python3 scripts/isochrone_trial.py \
  --region zanzibar_tanzania \
  --origin-name "<exact catalog venue name>" \
  --minutes 30 \
  --fixture data/isochrone_fixtures/zanzibar_30m.geojson
```

Live mode (owner only; skipped in CI):

```
python3 scripts/isochrone_trial.py \
  --region zanzibar_tanzania \
  --origin-name "<name>" \
  --minutes 30 \
  --live
```

Live mode reads `TB_GOOGLE_MAPS_API_KEY` from the environment, POSTs to
the Isochrones generate endpoint, never prints the key, and prints the
same summary as fixture mode. On HTTP or parse failure, exit non-zero
with a clear message; do not fall back silently in `--live`.

Fixture mode never opens a network socket.

### 5.2 Comparison rules

- Haversine reachable: `walking_minutes(origin, venue) <= minutes`
  (same helper as production).
- Isochrone reachable: venue lat/lng inside the MultiPolygon (holes
  excluded).
- Print counts: both, haversine_only, isochrone_only, neither; and the
  venue names in haversine_only and isochrone_only (sorted).

### 5.3 Fixtures

Commit three minimal MultiPolygon fixtures (can be hand-simplified
shapes around real origin coords from the catalogs) at 30 minutes for
the three regions, plus one 15-minute and one 45-minute fixture for
Stone Town only. Document the origin lat/lng and minutes in
`data/isochrone_fixtures/README.md`. Fixtures are for CI logic proof;
the owner's live run replaces them as evidence later.

### 5.4 Owner runbook

`docs/briefs/ISOCHRONE_TRIAL_OWNER_RUN.md`: enable API in Cloud Console
(checklist), restrict key, PowerShell commands for the three regions at
15/30/45, and an empty results table (region, minutes, both, h_only,
i_only). Owner pastes counts only.

## 6. Tests (`tests/test_isochrone_trial.py`)

Exact names:

1. `test_point_in_polygon_respects_hole`
2. `test_haversine_set_matches_walking_minutes`
3. `test_fixture_mode_reports_symmetric_difference`
4. `test_live_flag_without_key_exits_nonzero` (env cleared)
5. `test_fixture_mode_does_not_open_network` (socket monkeypatch)
6. `test_touched_files_are_ascii`

## 7. R17

A. Break point-in-polygon to always true; `test_point_in_polygon_respects_hole`
   must fail. Restore.
B. Force fixture mode to attempt a network call; `test_fixture_mode_does_not_open_network`
   must fail. Restore.

## 8. Stop rules

Stop if F2/F3 are missing; if you need a new paid dependency; if you
are about to wire What Now or packing; if live mode would embed a key
in the repo.

## 9. Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

ruff 0.16.3. Zero failures expected. ASCII only.

## 10. Out of scope

- Product provider, cache, spend meter, What Now filter
- Drive / two-wheeler modes
- Map overlay
- Deploy, APK

## 11. Delivery

Commit on `feat/isochrone-trial`:
`trial: compare Haversine walk to Isochrones fixtures`.
Push; verify remote SHA. Do not merge. No `gh`.

## 12. Report

1. Base SHA. 2. Branch + remote SHA. 3. pytest last line. 4. ruff /
format / diff-check. 5. Files touched. 6. Example fixture-mode summary
for one region. 7. R17 A/B. 8. Confirmation no product path changed.
9. Exact owner live commands. 10. Anything unsure.
