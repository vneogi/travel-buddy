# Travel Buddy — Testing Guide

> Complete testing playbook for backend + Flutter app + end-to-end. Intended for
> a personal machine (no corporate VPN / registry restrictions). Keep updated as
> the app grows.

## 0. Prerequisites (one-time)

- **Python 3.11+** and the prod deps for live mode:
  `pip install -r requirements.txt` then uncomment/install: `litellm openai supabase stripe`
- **Flutter 3.2+**: install Flutter SDK, then `flutter doctor` and fix anything red.
- For device testing: **Android Studio** (SDK + an AVD emulator) or a physical
  phone with USB debugging. Web (Chrome) needs no emulator.
- Optional tools: `pip install pytest-cov schemathesis`, `dart pub global activate` not needed.

## 1. Backend — unit tests

```bash
pytest -q                      # expect: 21 passed, 5 skipped (Supabase, needs creds)
pytest --cov=. --cov-report=term-missing   # coverage (needs pytest-cov)
```
The 5 skips are `tests/test_supabase_integration.py` — they run only when
`TB_SUPABASE_URL` is set (see §8).

## 2. Backend — run it locally

```bash
# Dev auth (no JWT secret) — the app accepts an X-Debug-User-Id header.
# IMPORTANT: unset any real Supabase JWT secret so debug auth is active.
unset TB_SUPABASE_JWT_SECRET
export TB_DEBUG=true
uvicorn main:app --reload --port 8000
```
- Swagger UI: http://localhost:8000/docs — click-test every endpoint. Add header
  `X-Debug-User-Id: <uuid>` (use a real UUID, e.g. `11111111-1111-1111-1111-111111111111`).
- Smoke sequence: `GET /api/v1/health` → `POST /api/v1/trip/create` →
  `GET /api/v1/trip/{id}` → `POST /api/v1/trip/event` (event_type `ask_info`).

## 3. Backend — schema fuzzing (catch contract bugs before the app does)

```bash
schemathesis run http://localhost:8000/openapi.json \
  -H "X-Debug-User-Id: 11111111-1111-1111-1111-111111111111"
```
Property-tests every endpoint against its OpenAPI schema. Great for finding
serialization/validation mismatches the Flutter app would otherwise hit.

## 4. Flutter — fastest UI feel (Chrome, no emulator)

```bash
cd mobile
flutter pub get
flutter run -d chrome \
  --dart-define=TB_API_BASE_URL=http://localhost:8000 \
  --dart-define=TB_DEBUG_USER_ID=11111111-1111-1111-1111-111111111111
```
Click through all 9 screens. (Maps + RevenueCat are stubbed — web is fine.)
Run the backend (§2) in another terminal first.

### Mobile feel (emulator / device)
```bash
flutter devices                 # list emulator/phone
flutter run -d <deviceId> \
  --dart-define=TB_API_BASE_URL=http://10.0.2.2:8000 \
  --dart-define=TB_DEBUG_USER_ID=11111111-1111-1111-1111-111111111111
```
Real device gives the true feel: haptics, gestures, timeline reflow.

## 5. Flutter — unit + widget tests

```bash
cd mobile
flutter test                    # runs everything under test/
flutter test --coverage         # → coverage/lcov.info
genhtml coverage/lcov.info -o coverage/html   # view (needs lcov)
```
Tests use `mocktail` to stub the backend — no live server needed. Current
coverage: models (fromJson contract), repositories (parse + endpoint contract),
ItineraryController (403→upgrade, heads-up banner, error handling).

## 6. Flutter — end-to-end on a device (optional, higher fidelity)

- Add `integration_test` (official) or `patrol` (nicer selectors, handles native
  auth/permission dialogs) to `dev_dependencies`.
- Write a flow: launch → create trip → swap a card → assert the timeline updates.
- Run: `flutter test integration_test/`.

## 7. Visual regression (once the design stabilizes)

- `golden_toolkit` — snapshot each screen; CI fails if pixels drift.
- Flutter **DevTools** (bundled) — widget inspector + performance profiler
  (check the timeline animation for jank).

## 8. Live-integration gates (when you flip to Supabase / real keys)

- Supabase path: set `TB_SUPABASE_URL`/`TB_SUPABASE_KEY`, run
  `python seed_supabase.py`, then `pytest tests/test_supabase_integration.py -v`.
  Full flip steps: see `docs/PROJECT_STATUS.md §3`.
- Real auth: set `TB_SUPABASE_JWT_SECRET`; the app switches from X-Debug-User-Id
  to verified JWTs. Use a real Supabase access token from the app's auth flow.

## Known caveats
- Backend runs on **in-memory** storage until the Supabase flip — state resets
  on restart, not shared across processes.
- `weather_service`, `cost_tracker`, `rag_ingestion` are scaffolding, not wired
  into the request path (see PROJECT_STATUS.md).
