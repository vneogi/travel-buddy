# SPEC-53: Situation Chips (Decision Compass)

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Owner chose this as the first signature prototype (2026-11-16).
> Amends SPEC-46 (What Now) and SPEC-25 (trip Ask thread). Reuses their
> contracts; no new endpoint.

## Goal

Reduce typing when a traveller needs quick recovery, inside the existing
grounded, trip-scoped chat.

## Slice 1 (first)

- Three or four text-labelled chips in the existing chat, above the
  keyboard and scrollable.
- Each chip maps to a closed, tested intent that prefills the existing
  What Now preferences and sends through the existing What Now path. The
  prompt and the structured result persist in the existing thread.
- Draft chip set, each kept only if the engine can honour it today:
  "Quick break", "Low energy", "Head back", "Find shelter".
- A chip returns feasible choices or a clear "no grounded option found".
- Offline: the chip explains it needs a connection; nothing is queued.

## Constraints

- No claims about AC, rain, distance limits or opening status unless the
  engine has trusted fields and deterministic rules for them.
- No silent mutation. Any add, swap or cancel needs explicit review and
  confirmation. "Head back" proposes specific affected stops; it never
  cancels them directly.

## Dependency

The chat controller lifetime fix (PR #260, on main) must be on the
installed APK, because chips send through the same path that previously
dropped results when chat was opened from Home.

## Acceptance

- Chips are reachable, scrollable and accessible.
- Each chip maps to a tested closed intent; prompt and response persist.
- No unsupported claims; no mutation before confirmation; offline is
  clear and safe.

## Trip relevance

High.
