# Genie brief: SPEC-10 hotel coordinates from the catalog (slice 2)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA. Base on that SHA, which is `origin/main` at or after
`d3c02a3` (docs PR #317).

Owning spec: `docs/specs/SPEC-10-booking-anchors.md`, remainder "stay
interval semantics", open item "hotel geocode". Owner decision 2026-11-21:
catalog and bundled data only. No geocoding API, no new network call, no
new dependency, no new table, no migration.

CI is the gate. Owner Windows `pytest` and `flutter test` are allowed; do
not ask for a phone APK.

## 0. Why this exists

A hotel gets its origin and return coordinates from its lat/lng. Today the
only automatic source is `services/catalog_name_match.py`
`catalog_coords_for_name`, which needs an exact, case-insensitive, stripped
name match in the same region. Anything else keeps no coordinates, so the
hotel cannot anchor the morning origin or the evening return. A booking
named "Zanzi Hotel" misses a catalog row named "Zanzi Resort", and a name
edit does not look again.

## 1. Bound

- Deterministic only. Normalise names, then match against the same catalog
  the code already reads. No LLM. No network. No new catalog rows.
- Hotels only. Flights, trains and tours keep their current behaviour.
- Never overwrite coordinates the traveller or the parser supplied. The
  rule is "fill only when both lat and lng are absent", as today.
- Do not change `catalog_coords_for_name`'s exact-match result for any
  input that matches today. Widen only when the exact match fails.

## 2. Verified facts on `main` (re-verify in preflight; line numbers drift)

- `services/catalog_name_match.py` `catalog_coords_for_name(venue_name,
  geo_region, catalog_fn=None)`: exact match on `name` or `venue_name`,
  rejects rows whose `geo_region` differs, returns `(None, None)` on miss
  or on catalog error.
- Call sites in `agents/state_machine.py`:
  - add booking path, around line 721: hotel, both `lat` and `lng` absent,
    `bk_region` set.
  - edit path, around line 832: re-resolves only inside the city-change
    branch (`new_region` set), and clears `lat`/`lng` first.
- Preflight: confirm whether a title-only edit of a hotel re-resolves today.
  Record the answer in the PR description. Do not change the branch
  condition unless section 3 test 6 requires it.
- `services/ask_service.py` also reads `db.list_venues_for_region`. Do not
  change that call.
- Preflight: confirm the December hotels (Zanzi, the Stone Town and Nungwi
  stays) and whether each has a catalog row. Record the names and results
  in the PR description. Do not add rows.

## 3. Change

1. Add a pure function `normalise_venue_name(name) -> str` in
   `services/catalog_name_match.py`. Rules, in order:
   - lowercase, trim, collapse internal whitespace;
   - strip punctuation (keep letters and digits);
   - drop the generic hotel words `hotel`, `resort`, `lodge`, `inn`,
     `villa`, `guesthouse`, `hostel` only when they are not the whole name.
2. In `catalog_coords_for_name`, keep the exact match first. Only when it
   misses, compare normalised names. Return a result only when exactly one
   catalog row in the region matches. Two or more matches return
   `(None, None)`. Never guess between rows.
3. Hotels only, both call sites unchanged in shape. Do not touch flights or
   tours.
4. Name edit re-resolve (edit path): when a hotel's title changes and its
   coordinates were catalog-filled (not supplied), re-resolve from the
   catalog. If the new name misses, clear the catalog-filled coordinates.
   Never clear coordinates the traveller or parser supplied. "Catalog-filled"
   is decided by comparing the stored `lat`/`lng` with the catalog row the
   old name matched. If the old name had no match, keep the coordinates.
5. Logs: no venue names in new log lines (R-privacy: names can carry
   confirmation context). Counts only.

## 4. Tests (must fail on main)

Backend (`tests/test_spec10_hotel_catalog_match.py`), drive through
`POST /api/v1/trip/event` where the path is an event, and through the pure
function otherwise:

1. `normalise_venue_name("Zanzi Hotel!") == "zanzi"`; `"Hotel"` alone stays
   `"hotel"`.
2. Catalog row "Zanzi Resort", booking "Zanzi Hotel", same region: coords
   filled. Fails on main.
3. Exact match still wins: catalog has "Zanzi Hotel" and "Zanzi Resort";
   booking "Zanzi Hotel" gets the "Zanzi Hotel" coords.
4. Two rows normalise to the same name in the region: `(None, None)`; no
   guess.
5. Region mismatch: a normalised match in another region is rejected.
6. Title edit on a catalog-filled hotel re-resolves to the new catalog row
   (or clears when the new name misses). Preflight decides whether this
   path exists today; if it does not, this test is a new behaviour and must
   say so in the PR.
7. A hotel with coordinates supplied by the traveller keeps them through a
   title edit that misses the catalog.
8. Flight with a name that would match a hotel row: no coordinates added.
9. Catalog error (`catalog_fn` raises): `(None, None)`, no exception.
10. Offline / no-network guard: the path makes no HTTP call (patch
    `socket` or the Google client to raise; the test must still pass).

Flutter: none required. The sheet does not change. If a Flutter test
asserts on hotel coordinates from the response, list it in the PR.

Existing tests: do not change expected values. Stop if more than three
existing tests need expected-value edits.

R17: the PR branch is one backend commit plus, if needed, a test-only
commit. Push also:

- `feat/spec10-hotel-catalog-match-r17a`: from the PR tip, `normalise_venue_name`
  returns its input unchanged (no normalisation). Tests untouched.
  Expected failures: 1, 2, 6.
- `feat/spec10-hotel-catalog-match-r17b`: from the PR tip, the name-edit
  re-resolve is removed. Tests untouched. Expected failures: 6 only.

The planning agent opens each as a draft PR, reads the failing test names,
closes them unmerged and deletes the branches.

## 5. Explicitly out

- Any geocoding API, reverse geocoding, or a new network call
- New catalog rows, or editing catalog data files
- Fuzzy or LLM matching, edit-distance thresholds beyond the rules in
  section 3
- Early check-in and late check-out (spec: a later field)
- Flight, train or tour coordinates
- Changing `list_venues_for_region` or the Ask catalog reads
- Server-side document consent
- `pack_day`, reflow, or confirm logic (SPEC-10 slice 1 is on main)
- APK, Cloud Run, deploy
- New dependencies

## 6. Stop rules

- Stop if matching needs a new table, a migration, or a network call.
- Stop if the name-edit path cannot be made to clear only catalog-filled
  coordinates without a schema change.
- Stop if more than three existing tests need expected-value edits.
- Stop if the normalisation rule would match a flight or tour.

## 7. Gates

- ASCII only in added comments and strings (R14).
- No hard-coded test counts in docs (R16).
- `pytest` green in CI; focused file plus existing SPEC-10 booking tests.
- `ruff check` and `ruff format --check` clean.
- Jobs: `pytest`, `lint`, `postgres-proof`, `docker-build`, `test`, `flutter`
  green. `deploy` and `build` skipped. `android-compile` green.

## 8. PR

Branch `feat/spec10-hotel-catalog-match` from the base SHA you were sent.
One commit for the backend, or two if the test commit is separate. Do not
merge. Push the branch and the two `-r17a` / `-r17b` heads. Send the
planning agent the PR description (no `gh` on Genie compute); the planning
agent opens the PR.

The PR description must include: the preflight answers from section 2
(title-edit path, the December hotel rows), a test-to-production table, R17
expected failures, any existing test touched, and "no APK in this slice".

## Amendment 1 (planning agent, 2026-11-22, after Genie's preflight)

Preflight facts that change the slice:

- The base is `273fa7c` (`origin/main`, the commit that landed this brief).
- Section 2 was wrong about the edit path. Rule B7 in
  `agents/state_machine.py` already re-resolves on `_city_changed or
  _title_changed`, using the exact match, and it clears `lat` and `lng`
  first, including coordinates the traveller supplied. That clearing is the
  real bug.
- The catalog has no lodging rows. `data/zanzibar_tanzania.json` and
  `data/nungwi_tanzania.json` carry categories cafe, museum, activity,
  restaurant, walking_area, street_food, market, viewpoint, nature, bar,
  massage_spa only. No December hotel can match, exact or normalised.

Decisions:

1. Drop the normalised-name widening (section 3 items 1 and 2, tests 1 to 5)
   from this slice. A cafe or restaurant pin under a hotel is worse than no
   pin, a lodging filter has no rows to act on, and dormant code that real
   data cannot exercise is not worth carrying. It stays parked until hotel
   rows exist in the catalog. `catalog_coords_for_name` is unchanged.
2. Keep and fix the edit path (section 3 item 4). Title-only hotel edit:
   keep re-resolving with the exact match, but clear only catalog-filled
   coordinates. "Catalog-filled" means the stored lat/lng equal the row the
   old name matched. If the old name matched no row, or the stored lat/lng
   differ from that row, the coordinates are the traveller's or the
   parser's: keep them, whatever the new name matches. If the traveller
   supplied explicit `lat`/`lng` in the same edit, those win.
3. City change stays as it is: B7 clears old-city coordinates, then
   re-resolves. `test_edit_city_change_clears_old_coords` in
   `tests/test_g0_field_fix_proofs.py` is unchanged.
4. Replacement tests (`tests/test_spec10_hotel_catalog_match.py`), driven
   through `POST /api/v1/trip/event`:
   1. Title-only edit, supplied coords, old name matches no catalog row:
      coords kept. Fails on main.
   2. Title-only edit, supplied coords that differ from the row the old name
      matched: coords kept. Fails on main.
   3. Title-only edit, catalog-filled hotel, new name has an exact row:
      re-resolved to the new row.
   4. Title-only edit, catalog-filled hotel, new name misses: coords
      cleared.
   5. City change still clears and re-resolves (existing test stays green;
      add a pointer, do not duplicate it).
   6. A flight title edit never gains or loses coordinates.
   7. Catalog error during an edit: no exception, coordinates unchanged.
   8. No-network guard: the edit path makes no HTTP call.
5. R17 (replaces section 4's):
   - `-r17a`: restore the unconditional clear on title-only edit. Expected
     failures: 1 and 2.
   - `-r17b`: treat stored coordinates as catalog-filled whenever the old
     name matched a row, with no lat/lng comparison. Expected failures: 2
     only.
6. Existing tests: setup-only changes allowed, no expected-value edits. If a
   test needs an expected-value edit, stop and report.
7. Everything else in sections 1, 5, 6, 7 and 8 stands. "No new network
   call" now also means no geocoding on the December hotels.

December hotel coordinates are a data problem, not a code problem. They need
either hotel rows added to the catalog or owner-supplied pins. That waits on
owner on-site data and is not Genie work in this slice.
