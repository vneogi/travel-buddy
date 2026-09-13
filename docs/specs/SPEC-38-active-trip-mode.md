# SPEC-38: Active Trip Mode

> Status: DONE. Merged PR #59 as `fefc4ec`. Owner Android field pass
> 2026-09-14 against Cloud Run `travel-buddy-00004-62g`.
>
> Depends on the SPEC-36 corridor and SPEC-37 installed field path. This is a
> deterministic client-navigation slice. It does not add an LLM, memory layer,
> PDF import, or automatic itinerary mutation.

## Goal

When a trip is active, take the traveller to the relevant stop and make the
next safe action visible. The traveller should not have to hunt through city
sections or infer hidden gestures while standing in transit.

## Decisions

1. Home remains reachable. Tapping the featured Now/Up next card opens the
   itinerary with a `focus` node query; the app does not globally redirect `/`.
2. The itinerary expands the focused city and scrolls the requested node into
   view after cached or network data loads.
3. Unlocked pending activity cards show Cancel. Cancellation requires an
   explicit confirmation and uses the existing deterministic skip mutation.
   Locked booking anchors never expose this action.
4. Departure reminders carrying a node ID navigate to that stop.
5. Context alerts carrying affected node IDs offer View stop. Weather alerts
   whose suggested action is `review_outdoor_plans` also offer Review
   alternatives, which opens the existing swap sheet for the affected node.
6. A swap is never applied from an alert until the traveller chooses a venue.
7. Unknown or stale node IDs are safe no-ops. They do not select the first
   itinerary node.

## Acceptance

- Featured-trip navigation includes its actionable node ID.
- Focus works for corridor and single-city timelines.
- A collapsed past city expands before focus.
- Cancel is visible only for unlocked pending activities; declining leaves the
  trip unchanged and confirming sends one `cancel_activity`.
- Departure and weather actions target the affected node.
- Review alternatives opens the confirm-before-swap sheet and dismissal does
  not mutate the trip.
- The authoritative Laos corridor accepts Vientiane Oct 2-3, Vang Vieng Oct
  4-5, and Luang Prabang Oct 6-9 (8 days total).
- Flutter analyze/tests and Android compile remain green.

## Non-goals

- Automatic startup redirect away from Home.
- LLM provider switching, persistent chat, agentic memory, or vector recall.
- Too far, Too hot, Raining, or Too tired copilot actions.
- PDF intake, Day Sheet, print pack, OCR, or itinerary document storage.
- Single-city start and end dates. SPEC-32 still creates one catalog day from
  one `start_date`. A later Create Trip spec owns ranges plus party/interest
  screens.
