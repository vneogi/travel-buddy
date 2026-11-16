# SPEC-51: Unified Trip Creation

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Owns finding F1 in `docs/UX_BACKLOG.md`.
> Amends SPEC-36 (corridor trip) and SPEC-26 (home surface), reusing the
> SPEC-40 guided create wizard.

## Goal

One "Create a trip" entry on Home. A supported corridor is a preset inside
that flow, not a separate competing home card.

## Slice 1 (first)

- Remove the separate corridor card from Home; keep one create action.
- The destination step offers supported single regions and supported
  corridor presets, driven by the backend corridor registry. It must not
  imply arbitrary multi-city combinations are supported.
- A single destination uses the existing wizard. A corridor preset reuses
  the per-segment date form.
- A review step shows destinations in order, dates per segment and party.

## Owner decisions (2026-11-16)

- The separate Vientiane to Luang Prabang corridor card on Home goes.
  The corridor is a preset inside the single Create a trip flow only. No
  shortcut card is kept.
- Still parked until after the Tanzania trip. Brief not to be written
  before then.

## Constraints

SPEC-36 rules stand: no synthetic transfers or stays, and no relabelling
one city's venues. Corridor sequence and date validation stay
backend-authoritative. No new undocumented endpoint.

## Out of scope

Combining non-corridor regions such as Stone Town plus Nungwi. They stay
separate regions on purpose, because day plans do not cluster across them.

## Acceptance

- Home shows one clear create entry.
- Single-city and corridor creation both succeed through the unified flow.
- Tests cover preset selection, date validation, back navigation and
  existing create regressions; update the corridor and home tests.

## Trip relevance

Low. Both Tanzania trips already exist.
