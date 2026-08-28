# SPEC-29: Context Alerts

## Status: IN PROGRESS

## Summary

Deliver structured, evidence-backed, timestamped context alerts that expire.
Phase 1 source: OpenWeather forecasts matched to upcoming itinerary nodes.

## Alert Identity and Deduplication

- alert_id is a deterministic hash of (trip_id, alert_type, window_start, affected_node_ids).
- Equivalent alerts affecting the same forecast window are deduplicated.

## Evidence and Provenance

- Every alert carries typed evidence containing only values observed from the provider.
- source identifies the provider (e.g. "openweather").
- source_updated_at is the timezone-aware timestamp from the provider response.
- No LLM-generated content in evidence text.

## Timestamps

- valid_from / valid_until: forecast validity window (timezone-aware).
- expires_at: when to stop showing the alert (derived from forecast validity).
- observed_at == source_updated_at: when provider data was fetched.

## Affected Nodes

- affected_node_ids and affected_node_names identify itinerary nodes in the forecast window.
- Only pending, non-skipped nodes are considered.

## Location Basis

- location_basis: "node_coordinates" if the affected node has lat/lng, else "trip_region".
- Node coordinates take priority over region center.
- Device GPS is not used in Phase 1.

## Deterministic Thresholds

- Rain advisory: precipitation probability >= 0.50
- Storm warning: condition code in storm set {200-232, 771, 781}
- High heat advisory: feels_like_c >= 40
- Extreme heat warning: feels_like_c >= 45
- High humidity info: humidity >= 80 AND feels_like_c >= 35

## Stale/Offline Behavior

- Cached alerts with expires_at in the past are hidden.
- Provider unavailable: return 503 (never invent data).
- No API key configured: return status "unconfigured" with empty alerts.

## User Dismissal

- Dismissal is local (client-side) in Phase 1.
- Dismissed alert_ids are stored in SQLite, identity-scoped.

## No Automatic Itinerary Mutation (v1)

- Alerts are informational. No auto-swap, auto-cancel, or auto-move.
- auto_applied is always false.
- A user must confirm any structural event.

## Phases

1. Phase 1 (this PR): Refresh on itinerary load, app resume, manual refresh.
2. Phase 2 (future): Server-side scheduled watcher and push notifications.

## Explicit Constraints

1. Refresh triggers: itinerary load, app resume, manual pull-to-refresh.
2. Server-side watcher and push: Phase 2.
3. User must confirm any move/swap/cancel.
4. Cached expired alerts are hidden.
5. Synthetic transit data is never displayed as a factual alert.
