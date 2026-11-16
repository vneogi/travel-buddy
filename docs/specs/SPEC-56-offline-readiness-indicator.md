# SPEC-56: Offline Readiness Indicator

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Slice 1 brief: `docs/briefs/GENIE_SPEC56_OFFLINE_READINESS.md`.
> Amends SPEC-04 (offline vault), using SPEC-02 cache metadata.

## Goal

Tell travellers what is actually saved on the device before connectivity
is lost, without promising a full offline pack.

## Slice 1 (first)

- A compact status from existing cache metadata, for example "Saved on
  this device" with a timestamp, or "Offline; showing saved trip".
- A detail sheet lists only verifiable items: itinerary snapshot time and
  how many of the trip's stops have a saved driver card.
- The outbox holds analytics signals, not traveller edits, and has no
  identity scope, so its count is not shown here; it stays in Profile >
  Sync Status (decision 2026-11-16).
- Manual refresh where appropriate. No background download prompts.

## Constraints

- Never "100% offline ready". No claim that maps, emergency contacts, all
  venues or a city pack are downloaded unless that capability exists.
- Queries are bounded and never delay opening the itinerary.
- A full offline pack is out of scope until its content, size, licensing,
  freshness and download behaviour are specified.

## Acceptance

- Accurate on fresh cache, stale cache, no cache, online and airplane mode.
- Freshness reflects real cache metadata.
- Tests cover lifecycle refresh, stale cache, cache absence and pending
  sync.

## Trip relevance

High (patchy connectivity expected in Zanzibar and Nungwi).
