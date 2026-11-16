# SPEC-52: Existing-Trip Date Markers

> Status: PARTIAL (owning spec written 2026-11-16). Overlap markers in the
> create date picker are on main (finding F3 in `docs/UX_BACKLOG.md`).
> Remainder: activity span versus create-form dates in the trip summary.
> Amends SPEC-40 (guided create wizard, date step).

## Goal

Non-blocking awareness of date overlap while creating another trip.

## Rules (already the intent of F3)

- Dates covered by existing trips get a subtle marker with an accessible
  label. Selecting one shows a short overlap note.
- Overlap is never blocked and never treated as a booking conflict.
- Compare destination-local calendar dates, not UTC instants.
- Works from cached trip summaries when offline.

## Slice 1 (first)

A verification checklist against main for the rules above. Change code
only if a gap is found. Then decide whether the trip summary should show
the activity span instead of the create-form dates.

## Acceptance

- Markers render from cached summaries with accessible semantics.
- Overlap remains allowed.
- Tests cover start and end boundaries, multi-day spans, timezones,
  offline cache and multiple overlapping trips.

## Trip relevance

Low.
