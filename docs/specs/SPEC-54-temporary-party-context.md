# SPEC-54: Temporary Party Context and Energy

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Amends SPEC-03 (party context) and SPEC-46 (What Now).

## Goal

Let the trip captain set a temporary constraint for the group (for
example "Low energy" or "Prefer indoors") that applies across several
asks, without rewriting the saved party or touching locked commitments.

## Context

The What Now form already carries time budget and energy per ask. This
spec is about keeping a constraint active across asks with a visible
scope and expiry. It overlaps SPEC-53 and may become SPEC-53's second
slice.

## Slice 1 (first)

- Client-local only, scoped to trip and identity, cleared on trip change
  and sign-out.
- Visible while active, clearable at any time, with an explicit
  destination-local expiry. No silent midnight assumption when the trip
  timezone is unknown.
- Affects only future What Now and swap suggestions the engine can honour;
  never existing nodes, bookings or the schedule.
- Explains when a constraint cannot be honoured because data is missing.

## Owner decisions (2026-11-16)

- Storage: on this phone only, cleared on sign-out. No server
  persistence in this spec; SPEC-43 consent is needed before any change.
- Expiry: end of the current local day at the destination. Not a fixed
  number of hours. Not "until cleared" by default (the visible clear
  control still exists).
- Scope of slice 1: energy and indoors preference only. Walking distance
  is a later slice. Party size or children is out of scope until a SPEC-43
  review.
- Still parked until after the Tanzania trip; the design is now decided.

## Constraints

Server persistence needs SPEC-43 consent, retention, ownership and data
minimisation first. No assumed filters such as "no open water" or "low
walking" without curated attributes and deterministic rules.

## Acceptance

- No state leaks between trips or identities; expiry and clear are tested.
- Locked bookings and the existing itinerary are unchanged.

## Trip relevance

Medium.
