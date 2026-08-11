# SPEC-11: Forced-Choice Preferences

> Status: SPECIFIED. Not implemented.
>
> Migration numbering assumes 0011 (venues_rag columns) and 0012 (booking
> anchors, SPEC-10) land first. Renumber if that allocation changes.

## Goal

Capture discriminative preference data in about 20 seconds at onboarding, before
any behavioural history exists, by asking the user to choose between two real
venues rather than to describe themselves.

## Why forced choice, not a settings form

A checkbox form collects stated preferences, and stated preferences collapse:
users tick everything, so nothing discriminates. This repo already contains the
proof. In the curated Laos venue data, `audience` was tagged `solo_traveler` on
41 of 50 venues and `couple` on 38 of 50. A tag that applies to 82 percent of
rows carries no information. Self-reported preference forms fail the same way.

A forced choice is different because it produces a **rejected** alternative.
That is the same shape as the existing `reroute_accepted` and
`reroute_rejected` pair, so it trains the same ranker rather than needing a
separate model. It also solves cold start: the ranker has signal on day zero of
a trip instead of day three.

## Design decisions

1. **Pairs are venue-grounded, never abstract.** Do not ask "do you prefer quiet
   or lively". Show two real venues from the trip's `geo_region` with
   contrasting attribute vectors and ask which the user would rather do.
   Abstract adjective pairs collect answers people cannot honour in practice,
   and venue-grounded pairs reuse `venues_rag` so there is no new content to
   curate.

2. **New signal type `preference_choice`**, client-emittable, `value_json` of
   `{chosen_ref, rejected_ref, contrast_dimension}`. It rides the existing
   SPEC-02 outbox, so onboarding works on a plane with no signal. Registry entry
   in `models/signal_types.py` plus migration `0013` seeding `signal_type`, in
   the same commit, or the drift guard fails (R5).

3. **This spec captures choices only. It does not build a preference model.**
   The `user_preference` table and LLM extraction described in VISION section 22
   are explicitly deferred to post-Laos, consistent with the section 30
   discipline of shipping substrate before engine. There is no volume to derive
   from yet.

4. **One exception, for reciprocity:** `GET /api/v1/user/preferences` returns the
   tallied attribute counts from the user's own choices, so the Flutter profile
   can show "you lean quiet, authentic, budget". This is cheap, requires no
   ranker, and gives the user something back for the taps -- the VISION section
   14 reciprocity principle applied to onboarding rather than post-trip.

5. **Pair selection is deterministic and offline-computable.** New
   `services/preference_pairs.py` exposes `next_pair(geo_region, already_shown,
   seed)` which maximises attribute contrast: Jaccard distance over `vibe_tags`,
   plus a differing `price_band` or `indoor_outdoor` where available.
   Deterministic given a seed so tests assert exact output, and cheap enough to
   run on cached venues with no network.

6. **Refuse rather than degrade silently.** If a region has fewer than 8 venues,
   return an empty pair list and skip the flow. Serving near-duplicate pairs
   collects noise that looks like data.

7. **No free text, no PII.** Consistent with the project stance. Skipping the
   flow emits nothing; only completed choices produce signals.

## Placement

Onboarding, after mood selection and before the first itinerary. Eight to ten
pairs, one tap each, always skippable. Each choice emits immediately to the
outbox, so a user who abandons after three pairs still contributes three data
points.

## Tests

- `next_pair` is deterministic for a fixed seed, and never repeats a pair
  already shown
- The chosen pair genuinely maximises contrast against the candidate set
- A region with fewer than 8 venues returns no pairs
- `preference_choice` is accepted by `POST /signals` with the correct
  `value_json` shape, and rejected when `chosen_ref` equals `rejected_ref`
- Emitting while offline persists to the outbox before any network attempt, and
  syncs on reconnect
- Drift guard green: `preference_choice` present in both the Python registry and
  migration `0013`
- `GET /user/preferences` requires auth and returns only the caller's tallies

## Acceptance

- [ ] `preference_choice` in registry, `PAYLOAD_SHAPES`, and migration `0013`;
      drift guard green
- [ ] `services/preference_pairs.py` deterministic and covered
- [ ] Onboarding flow emits one signal per choice, skippable, offline-safe
- [ ] `GET /user/preferences` returns per-attribute tallies, auth-scoped
- [ ] Fewer than 8 venues in region means the flow is skipped, with a test
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean after Dart writes
