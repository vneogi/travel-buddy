# SPEC-49: Driver Handoff and Tanzania Language

> Status: PARTIAL (owning spec written 2026-11-16). Swahili-then-English
> language priority for Tanzania regions is on main (finding F2 in
> `docs/UX_BACKLOG.md`). Show-to-driver slice 1 brief:
> `docs/briefs/GENIE_SPEC49_SHOW_TO_DRIVER.md`. In-app shortcut and
> field-verified Swahili landmarks are not implemented.
> Amends SPEC-12 (Driver Card), with SPEC-13 for language order.

## Goal

Make the existing offline Driver Card easy to hand to a local driver, and
close the Tanzania language gap honestly.

## Slice 1: Show-to-driver mode (first)

- One tap in from the Driver Card, one clearly visible tap out.
- Large, high-contrast destination name and verified landmark or
  directions text; unrelated controls hidden.
- Normal orientation. No brightness override, no rotation, no OS tile and
  no lock-screen exposure in this slice.
- Renders from the SQLite cache with zero network calls.

## Slice 2: in-app shortcut

A faster route from the active trip to the cached Driver Card, inside the
app only (from the Nov 16 design themes draft). Never claim a card is
offline-ready unless it is cached.

## Landmarks (owner data, not code)

For `zanzibar_tanzania` and `nungwi_tanzania`, missing Swahili names or
landmarks fall back to English and say local text is unavailable. Nothing
is generated or implied as verified. Field-verified landmark text needs
the owner's on-site data.

## Constraints

SPEC-12 provenance tiers stand: generated or unconfirmed strings never
render as confirmed local claims. Rotation, brightness and OS surfaces
need a separate device and privacy review before any slice uses them.

## Acceptance

- Mode works offline, with large text, one tap in and out.
- Any display state changed by the mode is restored on exit, navigation,
  app interruption and error.
- Tanzania follows `sw` then `en`; missing or unverified data is labelled.
- Tests cover locale priority, provenance display, cache-only render and
  cleanup on dispose.

## Trip relevance

High for Zanzibar taxis.
