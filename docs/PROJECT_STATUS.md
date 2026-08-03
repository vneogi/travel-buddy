# Travel Buddy — Project Status & Handoff

> Single source of truth for where the backend stands and what remains.
> Last updated: 2026-08-03. Keep this file updated as milestones complete.

## 0. TL;DR

- **Backend**: functionally complete, hardened, 21 unit tests + 5 skipped
  (Supabase) integration tests. **Runs today on an in-memory datastore.**
- **AI**: live via OpenAI (gpt-4o heavy, gpt-4o-mini light, text-embedding-3-small).
- **Supabase**: schema + functions created, keys configured — **but the app is
  NOT using it yet** (in-memory by design). A deliberate 3-import flip + smoke
  test is required to switch.
- **Payments (Stripe/RevenueCat)**: code complete and fail-closed, but keys not
  set — deferred until the mobile app exists.
- **Frontend**: not started. Begins next.

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
| Tests | ✅ | `pytest -q` → 21 passed, 5 skipped (Supabase, need creds). |
| SQL schema | ✅ | 5 tables, 5 functions (`$$`-quoted), 7 indexes live in Supabase. |

---

## 2. API contract the Flutter app will use

Base path: `/api/v1`. Auth: `Authorization: Bearer <supabase_access_token>`
(in local dev with no JWT secret set, use header `X-Debug-User-Id: <uuid>`).

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| GET | `/health` | No | Health + stats |
| GET | `/user/status` | Yes | Tier + remaining reroutes (no user_id in path) |
| POST | `/trip/create` | Yes | Create itinerary (⚠ see note) |
| GET | `/trip/{trip_id}` | Yes | Get trip (owner-only, else 403) |
| POST | `/trip/event` | Yes | **Main endpoint** — cancel/swap/add/reroute/translate/ask_info/change_mood/weather_alert |
| GET | `/venues/search` | Yes | RAG venue search |
| GET | `/stats` | Yes | System analytics |
| GET | `/payment/plans` | No | Plans |
| GET | `/payment/status` | Yes | Subscription status |
| POST | `/payment/checkout` | Yes | Stripe checkout session |
| POST | `/payment/verify-purchase` | Yes | Mobile IAP verify (RevenueCat) |
| POST | `/payment/webhook/stripe` | sig | Stripe → server |
| POST | `/payment/webhook/revenuecat` | secret | RevenueCat → server |

**⚠ Frontend gotchas — read before building screens:**
1. **No WebSocket.** The BRD mentions `ws://api/v1/chat/{trip_id}`; it is NOT
   implemented. The Chat screen must call `POST /trip/event` over REST. (Add a
   WS endpoint later only if real-time streaming is required.)
2. **`/trip/create` ignores preferences** and returns a FIXED 5-venue Dubai
   sample itinerary (one locked). Personalized generation is a future task.
3. **`user_id` is never sent by the client** — it's derived from the token and
   ignored in request bodies.
4. **Reroute limit**: structural events return HTTP 403 with an upgrade prompt
   once the daily cap (5 free / 50 pro) is hit. UI should surface this.
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
  `"authenticated"` (matches `settings.jwt_audience`); if the project uses the
  newer asymmetric signing keys, JWKS verification is needed instead (not yet
  implemented — flag if so).

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

**Deferred by design:**
- Stripe + RevenueCat keys — Phase 3, when the mobile app can drive purchases.
  Set: `TB_STRIPE_SECRET_KEY`, `TB_STRIPE_WEBHOOK_SECRET`, `TB_STRIPE_PRICE_MONTHLY`,
  `TB_STRIPE_PRICE_YEARLY`, `TB_REVENUECAT_API_KEY`, `TB_REVENUECAT_WEBHOOK_AUTH`.
  RevenueCat also needs a Google Play Developer account ($25 one-time).
- OpenWeather (`weather_service`) not wired into the request path.
- `weather_alert` / `change_mood` events route to the LLM but do NOT auto-swap
  the itinerary (needs indoor/outdoor venue metadata).

**Nice-to-have / low priority:**
- Deprecation warnings: Pydantic `class Config` → `ConfigDict`,
  `@app.on_event` → lifespan handlers, `datetime.utcnow()` → `datetime.now(UTC)`.
- No WebSocket chat endpoint (see §2). Add if real-time streaming is desired.
- `/trip/create` personalization (currently fixed sample).
- Gemini dropped (invalid key format); gpt-4o-mini covers the light tier.

---

## 6. Testing

- Unit suite (key-free, in-memory): `pytest -q` → **21 passed, 5 skipped**.
- Supabase integration (needs creds): `pytest tests/test_supabase_integration.py -v`.
- The unit suite does NOT exercise the live OpenAI or Supabase paths — those
  need a key/creds-loaded environment. A green suite ≠ integrations verified.
- Process note: the coding agent has twice introduced regressions while making
  tests pass (SQL `$$`, then an auth-bypass). **Run a code review after each
  batch of changes, before deploying** — tests alone missed the auth bypass.

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
# CORS
TB_CORS_ALLOWED_ORIGINS=https://yourapp.com   # comma-separated; * = dev only
# Payments (Phase 3)
TB_STRIPE_SECRET_KEY=
TB_STRIPE_WEBHOOK_SECRET=
TB_STRIPE_PRICE_MONTHLY=
TB_STRIPE_PRICE_YEARLY=
TB_REVENUECAT_API_KEY=
TB_REVENUECAT_WEBHOOK_AUTH=
```

---

## 8. Commit history (fix arc, for context)

Security/auth, payments, real AI, scheduler+breaker, tests+SQL, then hardening
(CORS, atomic throttle, Supabase seeder + integration tests), then the
auth-bypass regression fix. See `git log` for exact SHAs. Latest security fix:
`security: Fix critical auth-bypass regression (X-Debug-User-Id)`.
