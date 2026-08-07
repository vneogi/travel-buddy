# SPEC-05 — Structured logging & error capture
*Implements roadmap item #7. Motivation: a 500 with no visible traceback cost ~2 hours of
debugging. In Laos there is no laptop terminal to scroll — errors must be visible from the phone.*

## Requirements
1. **No silent 500s.** A global exception handler logs the full traceback + request context.
2. **Readable from the device.** A debug endpoint returns recent errors so they can be viewed
   in-app/browser without a terminal.
3. **Request logging** with method, path, status, duration_ms.
4. **Never leak secrets** — no env vars, tokens, or keys in logs or responses.
5. Debug endpoint is **gated** (debug mode or authenticated) and capped in memory.

## Implementation
### B.1 `monitoring/error_log.py` (new)
In-memory ring buffer (cap 100) of recent errors:
`{ts, path, method, status, exc_type, message, traceback, request_id}`.
Cap prevents unbounded growth (same lesson as cost_tracker).

### B.2 `main.py` — handlers + middleware
- `@app.exception_handler(Exception)`: log `traceback.format_exc()` with method+path, append to
  the ring buffer, return a 500 with a `request_id` (no internal details in the body).
- `@app.exception_handler(RequestValidationError)`: log the validation detail (this class of bug
  is what bit us) and return the normal 422.
- Middleware: assign `request_id`, time the request, log
  `method path status duration_ms request_id`.
- Use Python `logging` (a real logger, not `print`) so output is greppable and redirectable.

### B.3 `GET /api/v1/debug/errors` (new, in a debug router)
Returns the ring buffer, newest first. Available when `settings.debug` is true OR the caller is
authenticated. **404 (not 403) when disabled**, so it isn't discoverable in production.

### B.4 Startup log line
On startup, log active config **without secrets**: debug mode, backend (in-memory vs Supabase),
whether an LLM key is present (boolean only — never the key), CORS origins.

## Tests
- Endpoint raising an exception → 500 with `request_id`; ring buffer gains an entry with traceback.
- Validation error → 422 and an entry is recorded.
- `/debug/errors` returns entries when debug on; 404 when off.
- No entry contains any `TB_*` env value (secret-leak guard).
- Ring buffer never exceeds 100 entries.

## Out of scope
External APM (Sentry), log shipping, persistent log storage.

## Review checklist
- [ ] Traceback logged for every unhandled exception
- [ ] Response body contains no internal detail beyond `request_id`
- [ ] No secrets in logs or `/debug/errors`
- [ ] Debug endpoint 404s when disabled
- [ ] Buffer capped
- [ ] Uses `logging`, not `print`
