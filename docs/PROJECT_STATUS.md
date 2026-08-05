# Travel Buddy — Project Status & Handoff

> Single source of truth for where the project stands and what remains.
> Last updated: 2026-08-05. Keep this file updated as milestones complete.

## 0. TL;DR

- **Backend**: functionally complete, hardened, 21 unit tests + 5 skipped
  (Supabase) integration tests. **Runs today on an in-memory datastore.**
- **AI**: live via OpenAI (gpt-4o heavy, gpt-4o-mini light, text-embedding-3-small).
- **Supabase**: schema + functions created, keys configured — **but the app is
  NOT using it yet** (in-memory by design). A deliberate 3-import flip + smoke
  test is required to switch.
- **Payments (Stripe/RevenueCat)**: code complete and fail-closed, but keys not
  set — deferred until mobile payments phase.
- **Flutter mobile app**: ✅ **RUNNING END-TO-END** against local backend.
  31+ files, all 9 screens reachable, 14 Flutter unit tests passing.
  First successful `flutter run -d chrome` achieved 2026-08-05.

Do NOT treat this as production-ready. See §5 (blockers) before any public deploy.

---

## 1. What is DONE (verified)

| Area | Status | Notes |
|---|---|---|
| Auth (Supabase JWT) | ✅ | JWT verified server-side; identity from `sub` claim, never client input. Fails closed (`debug` defaults `False`). Regression test guards the debug-header bypass. |
| Trip CRUD + event loop | ✅ | Create / get / event, ownership-enforced. |
| Guardrail levers 1–5 | ✅ | Throttle (atomic), semantic cache (LIGHT only), circuit breaker (fires), asymmetric routing, sponsored boost. |
| Real AI | ✅ | Embeddings + LLM via OpenAI; auto-falls back to synthetic/canned if no key. |
| Scheduler | ✅ | Transit-aware reschedule, locked-reservation anchors, opening-hours re-check, hard-conflict detection. |
| Payments | ✅ (code) | Router mounted; Stripe sig-verified; RevenueCat webhook auth-verified; expiry checked; cancellation downgrades. Keys not set. |
| CORS | ✅ | Configurable via `TB_CORS_ALLOWED_ORIGINS`; no invalid `*`+credentials combo. |
| Persistence layer | ✅ (code) | Both in-memory and Supabase backends implemented behind `db_provider`. In-memory active. |
| Backend tests | ✅ | `pytest -q` → 21 passed, 5 skipped (Supabase, need creds). |
| SQL schema | ✅ | 5 tables, 5 functions (`$$`-quoted), 7 indexes live in Supabase. |
| Flutter mobile app | ✅ | Full scaffold: 9 screens, Riverpod state, theme, API client, repositories. Running on Chrome against local backend. |
| Flutter tests | ✅ | 14 passing: models (fromJson), repositories (endpoint contracts), ItineraryController (state machine). |
| Animated timeline | ✅ | Keyed ListView + AnimatedSwitcher cross-fade; StateNotifier controller with processing, banner, reroute-limit handling. |
| Backend code review | ✅ | Weather API key fixed, cost_tracker memory leak fixed, forecast math fixed, scope honesty documented. |

---

## 2. API contract the Flutter app uses

Base path: (no `/api/v1` prefix — routes mount at root). Auth: `Authorization: Bearer <supabase_access_token>`
(in local dev with no JWT secret set, use header `X-Debug-User-Id: <uuid>`).

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| GET | `/health` | No | Health + stats |
| GET | `/user/status` | Yes | Tier + remaining reroutes (no user_id in path) |
| POST | `/trip/create` | Yes | Create itinerary (⚠ see note) |
| GET | `/trip/{trip_id}` | Yes | Get trip (owner-only, else 403) |
| POST | `/trip/event` | Yes | **Main endpoint** — cancel/swap/add/reroute/translate/ask_info/change_mood/weather_alert |
| GET | `/venues/search` | Yes | RAG venue search (`?query=&lat=&lng=&top_k=`) |
| GET | `/stats` | Yes | System analytics |
| GET | `/payment/plans` | No | Plans |
| GET | `/payment/status` | Yes | Subscription status |
| POST | `/payment/checkout` | Yes | Stripe checkout session (`plan_id`: pro_monthly/pro_yearly) |
| POST | `/payment/verify-purchase` | Yes | Mobile IAP verify (RevenueCat) |
| POST | `/payment/webhook/stripe` | sig | Stripe → server |
| POST | `/payment/webhook/revenuecat` | secret | RevenueCat → server |

**⚠ Frontend gotchas — read before building screens:**
1. **No WebSocket.** Chat uses `POST /trip/event` over REST only.
2. **`/trip/create` ignores preferences** and returns a FIXED 5-venue Dubai
   sample itinerary (one locked). Personalized generation is a future task.
3. **`user_id` is never sent by the client** — derived from the token.
4. **Reroute limit**: structural events return HTTP 403 with
   `{"detail": "daily_reroute_limit_reached"}`. Flutter catches this as
   `RerouteLimitException` → auto-pushes `/upgrade` route.
5. Responses may include a trailing `Heads up: …` line when the scheduler flags
   a closed venue or an unreachable locked reservation.

---

## 3. Pending BEFORE / WHEN the UI connects (backend-side)

### 3.1 Supabase flip (the big one) — do this to get real persistence
Currently every trip/user/event is in-memory and wiped on restart. To switch:

1. Confirm both SQL blocks ran in Supabase (they have): tables + `hybrid_venue_search`,
   `reset_daily_reroutes` (from `models/database.py`) and `increment_reroute`,
   `consume_reroute`, `check_semantic_cache` (from `supabase_service.py`).
2. **Seed venues** — `venues_rag` is EMPTY in Supabase. Run:
   `pip install supabase litellm openai && python seed_supabase.py`
   (requires `TB_LITELLM_API_KEY` so embeddings match query-time; refuses to run
   with synthetic embeddings). Without this, all swaps/reroutes return "no candidates".
3. **Flip 3 imports** — change `from services.database_service import db_service`
   → `from services.db_provider import db as db_service` in:
   - `routers/trip_router.py`
   - `routers/payment_router.py`
   - `agents/state_machine.py`
4. **Use real UUIDs.** `user_tiers.user_id` is `UUID`; dev id `"u1"` will be
   rejected by Postgres. Test with a real Supabase JWT (its `sub` is a UUID) or a
   UUID-shaped debug id.
5. **Run the guarded integration tests** with creds set:
   `pytest tests/test_supabase_integration.py -v` → should pass; venue count > 0.
6. **Smoke test**: create trip → restart process → GET trip (proves persistence)
   → run a light + a swap event → confirm rows land in `trip_states` / `event_log`.
7. Commit only after 5 + 6 are green.

### 3.2 Enable real auth for the mobile app
- Set `TB_SUPABASE_JWT_SECRET` (Supabase → Project Settings → API → JWT Secret).
  This flips the app from dev-header mode to real JWT verification automatically.
- Flutter obtains the Supabase access token (Supabase Auth: magic link / Google)
  and sends it as `Authorization: Bearer …`. Confirm the token's `aud` is
  `"authenticated"` (matches `settings.jwt_audience`).

### 3.3 Dependencies for prod mode
`requirements.txt` has `litellm`, `openai`, `supabase` commented out (in-memory
MVP mode). Uncomment/install them for any environment that uses real AI or
Supabase (local prod run, Railway, Cloud Run).

---

## 4. Deployment checklist (when ready — Railway easiest)

- [ ] Set all `TB_*` env vars in the platform dashboard (see §7). Never commit `.env`.
- [ ] `TB_CORS_ALLOWED_ORIGINS` = the real web origin(s), comma-separated
      (NOT `*` in prod — credentials turn on automatically when it's not `*`).
- [ ] `TB_SUPABASE_JWT_SECRET` set (real auth) and `TB_DEBUG` unset/false.
- [ ] Supabase venues seeded (§3.1.2) in the target project.
- [ ] The 3 import flips committed (§3.1.3) and smoke-tested.
- [ ] Install prod deps (§3.3).
- [ ] Verify `/health` returns 200 and venue count > 0 post-deploy.

---

## 5. Known blockers / deferred / tech debt

**Must-fix before public production:**
- Supabase path is unverified until §3.1 smoke test is run live (code correct on review).
- CORS must be set to real origins (currently defaults to `*`, dev-only).
- No rate limiting / request-size limits on the API beyond the reroute quota.

**Deferred by design:**
- Stripe + RevenueCat keys — when the mobile app can drive purchases.
- OpenWeather (`weather_service`) not wired into the request path.
- `weather_alert` / `change_mood` events route to the LLM but do NOT auto-swap.

**Scaffolded but NOT wired (dead code in current request path):**
- `weather_service.py` — API key bug fixed (now uses `TB_OPENWEATHER_API_KEY`),
  forecast math fixed (3-hour blocks), but not called by any endpoint.
  `weather_alert` events route to LLM without real weather data.
- `cost_tracker.py` — Memory leak fixed (MAX_EVENTS cap + 2-day rotation),
  efficient daily check, but not imported by any module.
  `/stats` reports cache/event counts, not cost.
- `pipeline/rag_ingestion.py` — Scrape→chunk→embed pipeline, but never stores
  results. Venues come from `seed_data.py` only. Scraping targets have ToS risk.

**Flutter — remaining work:**
- SwapSheet: wired to `applyEvent` with default vibes; full sheet interaction TODO.
- Map screen: placeholder (Google Maps key not set).
- RevenueCat paywall: scaffold (keys not set, `purchases_flutter` commented out).
- Supabase Auth in Flutter: magic link + Google Sign-In not wired (using debug header).
- `VenueSearchResult.distanceKm` / `.isSponsored` null until backend surfaces them.
- Font files: `assets/fonts/` commented out; using `google_fonts` package (network).

**Nice-to-have / low priority:**
- Deprecation warnings: `datetime.utcnow()` → `datetime.now(UTC)`.
- No WebSocket chat endpoint. Add if real-time streaming is desired.
- `/trip/create` personalization (currently fixed sample).
- Slide animations for timeline reflow (currently cross-fade only; add via
  `flutter_animate` or `implicitly_animated_reorderable_list` package).

---

## 6. Testing

### Backend
- Unit suite (key-free, in-memory): `pytest -q` → **21 passed, 5 skipped**.
- Supabase integration (needs creds): `pytest tests/test_supabase_integration.py -v`.
- See `docs/TESTING_GUIDE.md` for full playbook (schema fuzzing, E2E, etc.).

### Flutter
- `cd mobile && flutter test` → **14 passed**.
- `models_test.dart`: TripNode/TripEventResult/UserStatus fromJson contract,
  EventType wire values match backend.
- `repositories_test.dart`: getTrip endpoint+parse, sendEvent body shape
  (wire values, not enum names), searchVenues uses `query` not `q`.
- `itinerary_controller_test.dart`: StateNotifier state machine —
  load, event+banner, reroute-limit→flag, generic error→banner, network error.
- Tests use `mocktail` to stub the backend — no live server needed.

### Running locally (dev mode)
```bash
# Terminal 1 — backend
unset TB_SUPABASE_JWT_SECRET && export TB_DEBUG=true
uvicorn main:app --reload --port 8000

# Terminal 2 — Flutter (Chrome)
cd mobile && flutter run -d chrome \
  --dart-define=TB_API_BASE_URL=http://localhost:8000 \
  --dart-define=TB_DEBUG_USER_ID=11111111-1111-1111-1111-111111111111
```

---

## 7. Environment variable reference (`.env`, never commit)

```
# Core
TB_DEBUG=false                     # true only for local dev without JWT
# AI (OpenAI)
TB_LITELLM_API_KEY=sk-...          # powers gpt-4o, gpt-4o-mini, embeddings
# Supabase
TB_SUPABASE_URL=...
TB_SUPABASE_KEY=...                # anon/service key for DB client
TB_SUPABASE_JWT_SECRET=...         # enables real JWT auth
# Weather (not wired yet)
TB_OPENWEATHER_API_KEY=...         # OpenWeatherMap free tier
# CORS
TB_CORS_ALLOWED_ORIGINS=https://yourapp.com   # comma-separated; * = dev only
# Payments (deferred)
TB_STRIPE_SECRET_KEY=
TB_STRIPE_WEBHOOK_SECRET=
TB_STRIPE_PRICE_MONTHLY=
TB_STRIPE_PRICE_YEARLY=
TB_REVENUECAT_API_KEY=
TB_REVENUECAT_WEBHOOK_AUTH=
```

---

## 8. Commit history (recent, for context)

| # | Message | Files | Date |
|---|---|---|---|
| 16 | `feat(mobile): Flutter app scaffold — full UI + integration layer` | 31 | 2026-08-04 |
| 17 | `fix(mobile): Correct Dart interpolation + API contract alignment` | 10 | 2026-08-04 |
| 18-19 | `docs: TESTING_GUIDE.md` (conflict resolved) | 1 | 2026-08-04 |
| 20 | `fix(mobile): Replace AnimatedList with crash-free keyed ListView` | 1 | 2026-08-05 |
| 21 | `fix: Backend review — API key bug, memory leak, scope honesty` | 6 | 2026-08-05 |
| 22 | `feat(tests): Flutter test suite + comprehensive TESTING_GUIDE.md` | 5 | 2026-08-05 |
| 23 | `fix(weather): Syntax error — comment ate the for-loop colon` | 1 | 2026-08-05 |
| 24 | `fix(tests): autoDispose fix + mounted guards + comment out fonts` | 3 | 2026-08-05 |
| 25 | `fix(mobile): Flutter 3.22 compat — CardThemeData + missing _InputBar` | 2 | 2026-08-05 |
| 26 | `fix(mobile): Guard tokenProvider against uninitialized Supabase` | 1 | 2026-08-05 |
| 27 | `fix(mobile): Guard app_router redirect against uninitialized Supabase` | 1 | 2026-08-05 |
| 28 | `fix(mobile): ShimmerList overflow — Column → ListView.builder` | 1 | 2026-08-05 |

---

## 9. Production Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ Done | Synthetic MVP (in-memory, mock AI, all endpoints) |
| 2 | ⏳ Ready | Supabase flip (schema deployed, flip = 3 imports + smoke test) |
| 3 | ✅ Running | Flutter mobile app (scaffold + running E2E locally) |
| 4 | 🔜 Next | RevenueCat payments (keys + `purchases_flutter` uncomment) |
| 5 | 🔜 | Play Store launch (real auth, real persistence, real payments) |
