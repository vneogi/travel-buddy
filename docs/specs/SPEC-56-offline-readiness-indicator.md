# SPEC-56: Offline Readiness Indicator

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Amends SPEC-04 (offline vault), using SPEC-02 cache metadata.

## Goal

Tell travellers what is actually saved on the device before connectivity
is lost, without promising a full offline pack.

## Slice 1 (first)

- A compact status from existing cache metadata, for example "Saved on
  this device" with a timestamp, or "Offline; showing saved trip".
- A detail sheet lists only verifiable items: itinerary snapshot, cached
  place cards and last successful sync time.
- Pending outbox count is diagnostic and shown separately in plain
  language; it is not a readiness measure.
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
