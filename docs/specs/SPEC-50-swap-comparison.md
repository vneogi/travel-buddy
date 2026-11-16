# SPEC-50: Inspectable Swap Comparison

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Amends SPEC-17 (trust and verification) for evidence rules. The surface
> is the existing swap sheet.

## Goal

Help a trip captain compare one candidate with the current stop before
confirming a swap.

## Slice 1: client-only comparison (first)

- Current stop and one candidate in a vertical comparison that fits a
  360dp screen. The existing search and list flow stays available.
- Only fields already present in the response. Each dimension shows a
  sourced value or "not available". No score and no "better" claim.
- Reason text explains evidence ("fits before your 16:00 booking"), not an
  opaque ranking.
- "Next option" changes the comparison without mutating the itinerary.
  "Confirm swap" stays a distinct action through the existing command path
  and preserves locked bookings.

## Later dimensions

Route distance or duration, price band, accessibility or party fit, and
indoor or climate comfort each need a documented source, schema,
freshness rule and tests before they appear. No guessed catalog values.

## Acceptance

- No overflow at narrow widths or large text.
- Missing data is omitted or labelled unavailable.
- Browsing never mutates; confirm uses the existing authoritative path.
- Widget tests cover locked stops, missing dimensions, confirm and
  dismiss.

## Trip relevance

Low to medium.
