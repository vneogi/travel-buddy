# SPEC-53: Situation Chips (Decision Compass)

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Owner chose this as the first signature prototype (2026-11-16).
> Amends SPEC-46 (What Now) and SPEC-25 (trip Ask thread). Reuses their
> contracts; no new endpoint.

## Goal

Reduce typing when a traveller needs quick recovery, inside the existing
grounded, trip-scoped chat.

## Slice 1 (first)

- Four text-labelled chips in the existing chat, next to the What now
  button, scrollable, one tap sends.
- Each chip is a fixed bundle of the existing What Now settings and sends
  through the existing What Now path. The user bubble shows the chip
  label; the structured result persists in the existing thread.
- Final chip set (owner brief 2026-11-16, each maps to settings the
  engine honours today): "Quick break" (45 min, low energy, short walk,
  anything), "Low energy" (90 min, low, short, quiet), "Indoors" (90 min,
  normal, short, indoors), "Something to eat" (90 min, normal, normal,
  food). Exact table in `docs/briefs/GENIE_SPEC53_SITUATION_CHIPS.md`.
- Dropped from the draft: "Head back" (no return-to-hotel intent in the
  engine yet; a later slice) and "Find shelter" (the engine cannot know
  shelter or weather; "Indoors" is the honest label).
- A chip returns feasible choices or a clear "no grounded option found".
- Offline: the chip explains it needs a connection; nothing is queued.

## Constraints

- No claims about AC, rain, distance limits or opening status unless the
  engine has trusted fields and deterministic rules for them.
- No silent mutation. Any add, swap or cancel needs explicit review and
  confirmation. A later "Head back" chip would propose specific affected
  stops; it never cancels them directly.

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
