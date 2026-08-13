# SPEC-21: Upstream Contribution to OpenStreetMap

> Status: DECIDED IN PRINCIPLE. Not scheduled, and deliberately not on the path to
> the October field trial.
>
> This is a decision record rather than a feature spec. It commits to a direction
> and writes down the constraints that make it harder than it looks, so that when
> it is scheduled the licence terms and the community norms are not discovered
> late. It has no schema, no endpoint and no acceptance list; when it is scheduled
> it becomes a spec and this record becomes its rationale.
>
> Depends on SPEC-17. There is nothing to contribute until `attribute_claim`
> exists and field confirmations are flowing.

## The decision

We will contribute confirmed commodity facts back to OpenStreetMap, under the
traveller's own account and with their consent, once SPEC-17 is implemented.

## Why

1. **We are already collecting exactly what OSM wants.** SPEC-17 asks travellers
   to confirm a name in local script, whether a place still exists, wheelchair
   access, the plate on the door. Those are map facts. Upstream-quality data is a
   by-product of the verification loop we are building for our own reasons.

2. **We are a consumer of the commons.** SPEC-19 mines it, SPEC-20 seeds cities
   from it, and `CORRIDOR_COVERAGE` was measured against it. Coverage is thinnest
   in exactly the corridor cities we care about most, and in those cities our own
   users standing in front of the venue are the cheapest available source of
   improvement. A consumer that never contributes degrades the thing it depends
   on.

3. **It gives away the commodity and keeps the judgement.** A better base map
   helps everyone, competitors included. The derived layer -- observed dwell,
   transition cost, taste transfer, question routing -- is where the product
   actually lives, and none of it is contributable even in principle. So the
   thing we would be giving away is the thing that is not our advantage, in
   exchange for data quality and goodwill in the markets we are entering.

4. **The trust story has to be consistent.** An app whose entire pitch is trust,
   which takes from a volunteer dataset and returns nothing, has a story it would
   rather nobody told.

## What we would contribute, and what we never would

Eligible: names and `name:xx` in local script, existence and closure, coordinate
corrections, wheelchair access, and the commodity tags a traveller can read off a
sign.

Never, and this list is the point of the record:

- **Anything derived from behavioural signals.** Observed dwell time, lateness,
  rejection rates are our users' movements. They are not map facts, and
  publishing them would be a privacy failure dressed up as generosity.
- **Anything model-generated.** An `llm_generated` claim never leaves the system.
  Uploading a fluent guess to a shared dataset is pollution, and it would be
  attributable to us by name.
- **Anything subjective.** Vibe tags, audience fit, whether it is worth the trip.
  Not map data.

So the export filter is narrow and mechanical: `source` is `field_verified`, the
attribute is on the eligible list, and the claim is fresh under SPEC-17 decision
14.

## The constraints that make this non-trivial

1. **ODbL, and the risk is on the consuming side rather than this one.**
   Contributing is the easy direction. Our exposure comes from already consuming:
   producing recommendations from OSM data is most likely a Produced Work and
   needs attribution only, but seeding `venues_rag` from OSM plausibly creates a
   derivative database, and share-alike attaches to those if they are
   distributed. This record does not resolve that question and must not be read
   as having resolved it. It flags that the question exists, is already live
   because SPEC-20 seeds from OSM, and needs proper advice before anything ships.

2. **Edits belong to the traveller, not to us.** Two models are available:
   per-user OAuth, where the edit is attributed to the person who made the
   observation, or a single application account. The first is correct and the
   second is convenient. The OSM community treats app-owned bulk accounts with
   justified suspicion, and uploading somebody's confirmation under our name is
   also a consent problem. Per-user OAuth, opt-in, visible before it is sent.

3. **Community norms are not optional.** Mechanical and batched editing has a
   published code of conduct with a process: discussion first, a documented
   changeset comment, a rate a human reviewer can actually follow. Skipping it
   gets the account blocked and the app named, which converts a goodwill exercise
   into a reputational cost.

4. **A contributed claim must not come back and outrank itself.** SPEC-17 ranks
   `osm` above `review_extraction`. If we push a single field confirmation
   upstream and later re-import it as an OSM value, we have laundered our own
   weak claim into a stronger source and destroyed the meaning of the ranking. So
   every contribution records its changeset, and the importer drops any OSM value
   whose provenance traces back to us.

5. **The export bar is higher than the display bar.** A wrong fact in our
   database is one bad recommendation. The same fact in OSM is in every
   downstream map, indefinitely. Displaying on one field confirmation is
   acceptable; exporting on one is not. Export requires corroboration by
   independent contributors.

## Sequencing

After SPEC-17, and after a field trial has produced real confirmations. There is
no version of this that is urgent, and every version of it is embarrassing if
rushed.

## Prior art

Every Door and OpenStop are both OpenStreetMap editors written in Flutter, so the
authenticated-edit and changeset machinery exists as working reference
implementations. Both are GPL-3.0: read them, do not copy from them.

## Revisit if

- Licence advice finds our consumption model riskier than assumed. That would
  make the OSM dependency itself the question, and this contribution the smaller
  half of it.
- Field confirmations prove too sparse to corroborate, which would make export
  unsafe by constraint 5 and leave this record correct but inert.
