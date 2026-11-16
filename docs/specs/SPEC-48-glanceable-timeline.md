# SPEC-48: Glanceable Timeline and Connectors

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Amends SPEC-45, which owns visible itinerary information architecture.
> Source: `docs/briefs/UI_UX_IMPLEMENTATION_SPECS_2026-11-15.md` and the
> Nov 16 design themes draft ("timeline as an instrument").

## Goal

Let a traveller see at a glance what is happening now, what comes next,
and whether there is time to get there, without a map-first shell and
without changing schedule generation.

## Slice 1: NOW and UP NEXT (first)

- The active stop gets a clear "NOW" label, title, destination-local time
  and one primary action, using existing design tokens. It must not push
  the next stop below the fold.
- When nothing is active, the next stop is labelled "UP NEXT" with its
  destination-local start time.
- Works from the cached itinerary when offline.
- Client only. No new network call and no backend field.

## Slice 2: connectors (waits)

- A compact connector between consecutive eligible cards, showing mode and
  duration only when a trusted route result provides them. Otherwise no
  estimate is shown.
- Owner decision 2026-11-16: connectors wait until a trusted per-leg
  duration source is chosen. None is assumed. The Isochrones provider
  gives a reachable area, not a per-leg time, so it does not qualify.
- No connectors on hotel continuation rows or across city sections.

## Out of scope

Map-first shell, decorative maps, new schedule warnings computed from
guessed travel time, schedule generation changes.

## Acceptance

- Current and next are distinguishable at a glance, including offline.
- No fabricated walk or drive estimate anywhere.
- Existing reflow, booking locks, corridor grouping and offline tests stay
  green; stable node keys are preserved.
- Long venue names and 200% text scale cause no horizontal overflow;
  "Now" and "Up next" have screen-reader semantics; 44dp targets.

## Trip relevance

Medium. Slice 1 helps on the day in Zanzibar and Nungwi.
