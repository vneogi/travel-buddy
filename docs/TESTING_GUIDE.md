# Travel Buddy -- Testing Guide

> Testing playbook for the backend, the Flutter app, and end-to-end. Written for
> a personal machine with no corporate VPN or registry restrictions.

## 0. Prerequisites (one-time)

- Python 3.11+ and the production deps: `pip install -r requirements.txt`.
  Live mode additionally needs `litellm openai supabase`.
- Test deps are pinned in `requirements-dev.txt`. Install them, because an
  ephemeral environment that silently loses `pytest-asyncio` turns eight real
  tests into skips while the summary still looks healthy (R8).
- If pytest dies instantly complaining about an unknown warning class, you are
  running some other interpreter's pytest and have not installed the dev
  requirements. Naming a class in a `filterwarnings` entry requires that class
  to exist, and `PytestReturnNotNoneWarning` is absent from pytest 8.4.0 --
  present in 7.2 through 8.3, deleted by accident in 8.4.0, restored in 8.4.1.
- Flutter 3.35+ with Dart 3.9+: required by the SQLite 3 web worker adapter.
  Install the SDK, run `flutter doctor`, and fix anything red.
- For client testing: Windows desktop or Android (AVD or physical phone) is the
  field target. Chrome is optional for layout only; web SQLite is experimental.
- Optional: `pip install pytest-cov schemathesis`.

## 1. Backend unit tests

    pytest -q -ra
    pytest --cov=. --cov-report=term-missing    # needs pytest-cov

No expected count is recorded here on purpose -- a mirrored number goes stale
and erodes trust in the whole document (R16). What matters is that `-ra` prints
a named reason for every skip, and that the reasons are ones you expect.

The expected skips are the live-database tests in
`tests/test_supabase_integration.py`, which skip with the reason "Supabase creds
not configured" when `TB_SUPABASE_URL` is unset. A skip anywhere else is a
finding: eight tests once degraded from passing to skipped when `pytest-asyncio`
vanished from an ephemeral environment, and the summary line still read as
healthy (R8).

Two config-level guards back that rule up, and they cover different failures.
An async test with no plugin installed fails outright -- that is pytest's own
behaviour from 8.4 onward and needs no configuration. A test that returns a
value instead of asserting is turned into an error by the `filterwarnings`
entry in `pyproject.toml`, because such a test passes while proving nothing and
pytest will never make it an error by default.

`tests/test_docs_hygiene.py` tests the documentation rather than the code. It
walks every markdown file outside build and vendor directories and fails on
non-ASCII bytes outside its allowlist, on a mirrored test count in a
load-bearing document, on architecture claims known to be false, and on a
`SPEC-NN` reference with no matching file. If it fails after you edit a
document, the document is wrong, not the test. The allowlist is permitted to
shrink and never to grow.

Passing tests are not verification (R3). Two of the worst defects in this repo
shipped green: an auth bypass, and a sync engine that string-matched on error
text and therefore retried 401s forever.

## 2. Run the backend locally

    # Dev auth: the app accepts an X-Debug-User-Id header.
    # Unset any real JWT secret or debug auth stays inactive.
    unset TB_SUPABASE_JWT_SECRET
    export TB_DEBUG=true
    uvicorn main:app --reload --port 8000

Swagger UI is at http://localhost:8000/docs. Add the header
`X-Debug-User-Id: 11111111-1111-1111-1111-111111111111` (it must be a real UUID).

Smoke sequence: `GET /api/v1/health`, then `POST /api/v1/trip/create`, then
`GET /api/v1/trip/{id}`, then `POST /api/v1/trip/event` with `event_type`
`ask_info`.

Watch the startup log. It prints booleans for `llm_key_present`,
`supabase_configured` and `jwt_auth`, never values. If `supabase_configured` is
false you are on the in-memory backend and nothing you write will survive a
restart, no matter what the API returns (R11).

## 3. Schema fuzzing

    schemathesis run http://localhost:8000/openapi.json \
      -H "X-Debug-User-Id: 11111111-1111-1111-1111-111111111111"

Property-tests every endpoint against its OpenAPI schema. Good at finding the
serialization mismatches the Flutter client would otherwise hit first.

## 4. Flutter, fastest loop (Windows desktop or Android)

    cd mobile
    flutter pub get
    flutter analyze
    flutter run -d windows \
      --dart-define=TB_API_BASE_URL=http://127.0.0.1:8000

Run `flutter analyze` before anything else; it catches the compile errors that
have repeatedly reached commits. Start the backend from section 2 in another
terminal first. Chrome is useful for layout only, not Maps, airplane-mode or
durability acceptance. Flutter must not receive `TB_DEBUG_USER_ID`; SPEC-09
uses the persisted device UUID in `Authorization: Anonymous <uuid>`.

After any edit to a `.dart` file, run:

    grep -rn '\\$' mobile/lib

Only the two price strings in `upgrade_screen.dart` should match. An escaped
interpolation has silently broken the base URL, the Bearer token and a ValueKey
on three separate occasions (R1).

### On a device

    flutter devices
    flutter run -d <deviceId> \
      --dart-define=TB_API_BASE_URL=http://10.0.2.2:8000

`10.0.2.2` is the emulator's route to the host. A physical device needs the
laptop's LAN IP instead, which also matters for section 6.

## 5. Flutter unit and widget tests

    cd mobile
    flutter test
    flutter test --coverage
    genhtml coverage/lcov.info -o coverage/html    # needs lcov

Tests stub the backend with `mocktail`, so no live server is needed. They must
throw the same exception types production throws -- a test that threw
`Exception('401 ...')` instead of `UnauthorizedException` is precisely why the
retry bug survived a green suite (R3).

## 6. Airplane-mode durability drill (gates the Laos field test)

This is the drill that must pass before the trip, and the first attempt was
meaningless. The build was talking to the laptop over `adb reverse` on USB, and
airplane mode does not disable USB, so four hearts posted instantly to a
supposedly disconnected server (R7).

Build against the laptop's LAN IP, not `10.0.2.2` and not a USB tunnel:

    flutter run -d <deviceId> \
      --dart-define=TB_API_BASE_URL=http://<laptop-lan-ip>:8000

Then:

1. Confirm the failure mode is real. Enable airplane mode and watch the server
   log show no incoming requests. If requests still arrive, stop -- the drill is
   invalid.
2. Tap loved on five venues.
3. Force-kill the app. Reopen it. Hearts must still show as filled (SPEC-02
   durable hearts; verified on Windows Aug 30). Sync Status still calls
   `syncOnce()` without awaiting it before reading counts; do not treat a
   stale count as a hearts-persistence failure.
4. Re-enable the network. All five must sync.
5. Query the destination store for five rows. An `accepted=1` log line is not
   proof of persistence -- the sync engine once reported exactly that while
   `db_provider` pointed at the in-memory backend and every signal was discarded
   on restart (R11).

## 7. End-to-end and visual regression (later)

- `integration_test` or `patrol` for a full flow: launch, create trip, swap a
  card, assert the timeline reflows.
- `golden_toolkit` for per-screen snapshots once the design settles.
- Flutter DevTools for the widget inspector and for checking timeline animation
  jank.

## 8. Supabase and live-integration gates

The backend already resolves to Supabase whenever credentials are present;
there is no pending flip. `services/db_provider.py` decides at import time.

- Set `TB_SUPABASE_URL` and the service key, then run
  `pytest tests/test_supabase_integration.py -v`. Those are the tests that skip
  by default.
- Loaders: `python scripts/load_dish_glossary.py data/laos_dish_glossary.json`
  and `python scripts/load_venues.py <files> --geo-region <region>`. Check
  `docs/AWAITING_VERIFICATION.md` first; the venue loader has open defects that
  make an unqualified run fail.
- Real auth: set `TB_SUPABASE_JWT_SECRET` and the app switches from
  `X-Debug-User-Id` to verified JWTs. Use a real access token from the app's
  auth flow.

Before running any of these locally, pull and confirm the fix you expect is
actually in your working copy. A correct remote plus a stale local produces the
same failure as never having fixed the bug (R10):

    git pull origin main
    grep -n "<expected string>" <path>

## Known caveats

- In-memory mode resets on restart and is not shared across processes. Check the
  startup log to see which backend resolved.
- Legacy `weather_service.py` is still scaffolding. Context alerts use
  `weather_provider.py` with OpenWeather as of SPEC-29. `cost_tracker` and
  `rag_ingestion` remain unwired.
- Current open defects, including the venue loader ones, are listed in
  `docs/AWAITING_VERIFICATION.md`.
