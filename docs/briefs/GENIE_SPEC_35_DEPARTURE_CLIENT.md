# Genie Brief: SPEC-35 Phase A2 In-App Departure Client

> Status: HISTORICAL, COMPLETED IN PR #52 (`1379da8`). Do not execute this
> brief again.

## Read first

- `docs/specs/SPEC-35-proactive-itinerary-notifications.md` (In-app client)
- `docs/specs/SPEC-29-context-alerts.md`
- `models/notifications.py`
- `routers/notifications_router.py`
- `mobile/lib/features/alerts/alerts_notifier.dart`
- `mobile/lib/widgets/alert_card.dart`
- `mobile/lib/data/context_alert.dart`
- `mobile/lib/features/itinerary/itinerary_screen.dart` (`_AlertsSection`)
- `mobile/lib/offline/offline_database.dart` (alert cache/dismissals)
- `mobile/test/features/alerts/context_alerts_test.dart`

## Scope

Implement only the Flutter in-app banner for SPEC-35 departure candidates.
The backend is already on main (PR #50). Do not change Python evaluators,
route/weather providers, trip creation, or `/alerts`.

Do not implement OS push, device tokens, background jobs, GPS, meal
previews, maps hand-off, or itinerary mutation.

## Required shape

Add:

- Dart models for `GET /api/v1/trip/{trip_id}/notifications`
  (`notification_id`, `type`, `priority`, `node_id`, `title`, `message`,
  `eligible_at`, `expires_at`, `recommended_departure_at`, `time_zone`,
  `deep_link`, nested `evidence.route|weather|policy`, top-level `status`).
- Identity-scoped SQLite cache + `notification_dismissals` table. Do not
  store notification IDs in `alert_dismissals`.
- A Riverpod family notifier that fetches `/trip/$tripId/notifications`.
- A compact banner widget above the itinerary timeline.
- Widget/unit tests and the named sabotage proofs below.

Reuse the SPEC-29 fetch/error pattern:

- 401/403: never use cache.
- Network / HTTP 503: unexpired cache allowed.
- Parse/programming errors: do not silently use stale cache.
- Resume refresh uses the same 15-minute debounce helper as alerts
  (`alertResumeRefreshDue` or a shared rename). Do not spam the endpoint
  on every resume.
- Loading must not replace the itinerary with a spinner.

Wire the existing alerts refresh control so one tap refreshes both
`/alerts` and `/notifications`. Do not add a second refresh button.

## Render rules

1. Show at most one `departure_reminder` that is not expired and not
   dismissed.
2. Ignore `meal_preview` and any other type.
3. Paint server `title` and `message` exactly. Do not compose new copy
   from evidence fields.
4. Optional caption: route source, plus weather source when present.
5. While a departure banner is visible, hide SPEC-29 weather cards.
   When none is visible, leave weather cards unchanged.
6. Dismiss persists locally and hides that `notification_id` after resume.
7. Tap scrolls to `node_id` if that node is in the current trip; otherwise
   no-op. Do not open maps, request location, swap, or cancel.
8. `status: unconfigured` and empty/partial with no candidate: render
   nothing. No error colour.

Trip-critical leave-now is not gated by `InterruptionBudget`. Do not call
`InterruptionBudget.request` to hide a due departure reminder.

## Do not

- Do not call `/notifications` from Home, Chat, or Driver Card.
- Do not request location permissions.
- Do not invent `current traffic` or rain sentences in the client.
- Do not mutate nodes or consume reroute quota.
- Do not add FCM/APNs, local OS notifications, or a watcher.
- Do not change backend copy, eligibility, or timezone logic.
- Do not rewrite historical briefs.

## Required proof cases

- Parses a fixture matching the PR #50 response shape, including nested
  evidence and `time_zone`.
- Expired candidate is hidden.
- Dismissed ID stays hidden after a simulated resume/rebuild.
- `meal_preview` in the payload is ignored.
- Visible departure hides weather cards; absent departure leaves weather
  cards visible.
- Banner text equals server `title` and `message` (sabotage: client-side
  rewrite must fail).
- 401/403 does not render cached departure copy.
- Network failure with unexpired cache still shows the cached banner.
- Resume inside 15 minutes does not issue a second notifications request.
- Tap on a known `node_id` requests scroll/focus; unknown id is a no-op
  with no maps launch.

## Sabotage proofs

1. Hard-code a client suffix onto `message`.
   - Named test that banner text equals server message must fail.
2. Keep SPEC-29 cards visible while a departure banner is shown.
   - Named stacking test must fail.
3. Skip persisting `notification_dismissals`.
   - Named dismiss-survives-rebuild test must fail.

## Completion report

Return:

- branch name;
- head SHA;
- pull request URL (open the PR; do not merge);
- files changed;
- `flutter analyze` / `flutter test` results, or explicit CI deferral if
  no Flutter SDK;
- pytest/docs hygiene if docs changed;
- named sabotage proofs.

PR title: `feat: show in-app departure notification banners`
