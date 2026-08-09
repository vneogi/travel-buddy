# SPEC-07: Client Signal Emission

## Goal

Wire the Flutter client to emit ALL client-emittable signal types at the
appropriate interaction points. Currently only `user_loved` is emitted.
This is the moat data — the behavioral flywheel that makes the product
learn from use.

## Signal types (client-emittable)

| Type | Trigger | value_text | value_json |
|------|---------|------------|------------|
| user_loved | Heart tap on venue | "loved" | — |
| reroute_accepted | Accept swap suggestion | — | {replacement_ref} |
| reroute_rejected | Dismiss swap sheet | — | {rejected_refs: [...]} |
| visited_confirmed | "I'm here" tap or geofence | "true" | — |
| node_skipped | Skip button + reason picker | — | {reason: <closed set>} |
| dish_loved | Heart tap on dish | "loved" | {dish_name} |
| dish_ordered | "Ordered" tap on dish | "true" | {dish_name} |

`arrival_delta` is SERVER_DERIVED and never emitted by the client.

## Implementation

Typed methods added to `SignalService` (mobile/lib/services/signal_service.dart):
- emitUserLoved
- emitRerouteAccepted
- emitRerouteRejected
- emitVisitedConfirmed
- emitNodeSkipped (with assert on reason ∈ closed set)
- emitDishLoved
- emitDishOrdered

All delegate to the existing `emit()` which handles:
- UUID v4 signal_id generation
- Outbox persistence (SQLite, before network)
- SyncEngine trigger (fire-and-forget)
- Queue cap enforcement (5000)
- Never-throw guarantee

## UI call sites

- Trip itinerary card: heart → emitUserLoved
- Swap suggestion sheet: accept → emitRerouteAccepted, dismiss → emitRerouteRejected
- Node detail: "I visited" → emitVisitedConfirmed
- Node card: skip button → reason picker → emitNodeSkipped
- Dish card: heart → emitDishLoved, "Ordered" → emitDishOrdered

## node_skipped reasons (closed set)

too_far, too_tired, closed, crowded, not_interested, ran_out_of_time, weather

UI must present a picker, never free-text. Unanalyzable free-text defeats
the purpose.

## Acceptance

- [ ] All 7 typed emit methods on SignalService
- [ ] node_skipped asserts reason ∈ closed set
- [ ] validSkipReasons constant matches Python NODE_SKIPPED_REASONS
- [ ] smoke-test.ps1 verifies all types accepted by server
- [ ] Suite green (R8)
