# SPEC-06 — Behavioral Signal Types

*Registers the behavioral signal types server-side with one source of truth,
writes the two missing migrations (0003 trip_party, 0004 signal types), and
adds a drift guard test that fails CI if registry and migrations disagree.*

## Status: IMPLEMENTING

## Why this matters

DATA_MODEL §4.2 specifies 7 signal types. Only `user_loved` is registered.
The other 6 would be rejected 422 today. Without them, the Laos field test
captures only heart-taps — one signal type out of the 10+ that make the data
asset unique. Reroute acceptance data is what no competitor has.

## Scope

**IN:** Register 5 new signal types server-side (reroute_accepted, reroute_rejected,
visited_confirmed, node_skipped, arrival_delta). Single-source-of-truth module.
Drift test. Two migrations (0003 completes SPEC-03, 0004 registers types).
Server-derived type guard (arrival_delta cannot be POSTed by client).

**OUT:** Client emission (SPEC-07). `dwell_minutes` (needs background location —
post-Laos). Client-side party picker UI. Arrival_delta derivation logic (needs
visited_confirmed events flowing first).

## Design decision: kill the registry drift structurally

Per ENGINEERING_RULES.md R5: "Never mirror a registry by hand across two files."

Before SPEC-06:
- `database_service.py:36` had `_valid_signal_types = {"user_loved"}`
- `supabase/migrations/0002*.sql` had `INSERT INTO signal_type ... 'user_loved'`
- Two files, one truth, drift is inevitable.

After SPEC-06:
- `models/signal_types.py` is the SINGLE source of truth
- `database_service.py` imports from it (no hardcoded set)
- `tests/test_signal_types.py` parses the migration SQL and asserts the key sets match
- Drift now fails CI, not silently in production.

## Files changed

| File | Change |
|------|--------|
| `models/signal_types.py` | NEW — canonical registry |
| `services/database_service.py` | Import from signal_types, remove hardcoded set |
| `routers/signal_router.py` | Add SERVER_DERIVED_TYPES rejection guard |
| `supabase/migrations/0003_trip_party.sql` | NEW — completes SPEC-03 |
| `supabase/migrations/0004_behavioral_signal_types.sql` | NEW — registers 5 types |
| `tests/test_signal_types.py` | NEW — drift guard + acceptance + rejection tests |

## Signal types registered

| Type | value_kind | Client-emittable | Notes |
|------|-----------|-----------------|-------|
| `user_loved` | none | Yes | Existing (0002) |
| `reroute_accepted` | replacement_ref | Yes | Core ranking-training signal |
| `reroute_rejected` | rejected_refs | Yes | User declined all swap suggestions |
| `visited_confirmed` | none | Yes | Ground truth: plan was followed |
| `node_skipped` | reason | Yes | Ground truth: plan was abandoned |
| `arrival_delta` | minutes | **No** (server-derived) | Schedule realism metric |

## Server-derived types

`arrival_delta` is derived server-side from the timestamp of a `visited_confirmed`
signal vs. the planned start time of that node. Clients cannot forge schedule-realism
data — if a client POSTs `arrival_delta`, it receives a per-item rejection:

```
{"signal_id": "...", "reason": "'arrival_delta' is derived server-side and cannot be submitted"}
```

## Migration 0003 (trip_party)

Completes SPEC-03. Creates `trip_party` and `party_member` tables that
`supabase_service.save_trip_party` expects. Until this migration is applied,
the Supabase flip is blocked.

## Migration 0004 (behavioral signal types)

Inserts the 5 new types into `signal_type` with `ON CONFLICT (key) DO NOTHING`.
Safe to re-run. Keys must match `models/signal_types.py` exactly — the drift
test enforces this.

## Acceptance criteria

- [x] `models/signal_types.py` is the only hardcoded list
- [x] `grep -rn '_valid_signal_types' services/` shows no literal set of names
- [x] `0003` and `0004` exist
- [x] Drift test fails if a type is added to only one place
- [x] Client cannot POST `arrival_delta` (per-item rejection)
- [x] Full suite green
- [x] R2: grep output pasted for each new/changed block

## What's next

**SPEC-07 (client emission):** Wire the Flutter app:
- Swap-accept → `reroute_accepted`
- Swap-abandoned (back button) → `reroute_rejected`
- Manual "I went here" tap → `visited_confirmed`
- Server derives `arrival_delta` from `visited_confirmed` timestamp vs. planned time
