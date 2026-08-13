# SPEC-18: On-Demand Venue Discovery

> Status: SPECIFIED. Not implemented. Depends on SPEC-17.
>
> No migration number is claimed. Numbers are taken at implementation time.

## Goal

A traveller standing somewhere asks "what is interesting about this place, is it
worth going in?" The app answers with the model, and the answer becomes a
provisional record, so the venue layer grows from real demand instead of from
pre-curation.

## Why this inverts the expensive part

SPEC-08 curated 58 Laos venues by guessing which would matter, and
docs/CORRIDOR_COVERAGE.md shows that effort had already exhausted what open data
knows about Luang Prabang. Pre-curation does not scale across a corridor of
cities, and it cannot anticipate the noodle stall a traveller actually walks past.

On-demand discovery reverses the order. Demand becomes the prioritisation
function, which beats a curator's judgement because it is measured rather than
assumed. Cost per venue decays: the first traveller at a place pays for a model
call and everyone after is served from what that call produced. And it makes
SPEC-20 much smaller, because the kit then only has to seed a city's spine.

## Design decisions

1. **Two tiers of place.** A `venue` has sourced identity, an external identifier
   and provenance, and may be recommended. A `venue_claim` is coordinate-anchored,
   model-described and unverified; it may be shown to the person who asked, marked
   as such, and may not enter recommendations for anyone else until promoted.

2. **Coordinate anchoring is mandatory.** The traveller is physically present, so
   we have a position -- the one advantage the batch loader never had. Before
   anything persists, cross-check the coordinate against OSM and Wikidata. With no
   external object within a small radius, answer the question but create no place
   record. A model will confidently describe places that do not exist, and an
   unanchored write path would poison the venue layer automatically and without
   limit.

3. **Identity resolves on the external identifier, never on the name.** The
   coordinate match yields an OSM or Wikidata id, and `venue_external_id` is the
   resolver. Twenty travellers asking about the same cafe must produce one record,
   and name matching cannot achieve that across transliterations.

4. **This is a second write path into the venue tables, and it reuses the loader's
   guards.** The same payload-versus-declaration guard, the same taxonomy
   validation against `taxonomy_term`, the same script checks. A runtime path that
   bypasses them is an unguarded ingestion route writing model output at scale,
   which is the Laos contamination reproduced mechanically.

5. **Model output enters as claims, never as venue fields.** Every descriptive
   sentence becomes an `attribute_claim` sourced `llm_generated`, subject to the
   SPEC-17 contract. The model does not get to write `category` or `price_band`
   directly.

6. **Be honest where the model is weak, and capture instead.** It is adequate on a
   famous temple and close to useless on an unmarked stall, because nothing in its
   training data describes one. There, say so and invite the traveller to tell us
   what they find. Somebody answering "was it worth it?" while standing there is
   the highest-value signal this product can collect, and refusing to guess is
   what earns the right to ask.

7. **Cost is bounded per traveller and per region.** Reuse the existing semantic
   cache and circuit breaker. A repeat question about a known place must not reach
   the model at all.

8. **Offline queues the question; it never fabricates an answer.** The ask needs
   network. Offline, the question persists in the SPEC-02 outbox and resolves on
   reconnect. Answering from nothing while offline is the worst available
   behaviour.

9. **Abuse and plausibility.** Rate-limit per traveller. A coordinate implausible
   against recent location history is not an anchor. Without this the flow is a
   free venue-injection endpoint.

10. **Promotion is derived, not manual.** A `venue_claim` becomes a `venue` on
    accumulated evidence: an external identifier match, independent questions from
    several travellers, a field confirmation, or signals showing people actually
    went. The rules live in the derived layer and are testable.

## Tests

- No external object near the coordinate means no place record is created, while
  the traveller still receives an answer
- Two questions about the same place from different travellers produce one record,
  resolved on external identifier
- Every persisted descriptive attribute carries source `llm_generated`
- The runtime path is rejected by the payload guard when it tries to write a key
  outside the declared write set
- A vocabulary value absent from `taxonomy_term` is refused
- A repeat question is served from cache with no model call
- Asked offline, the question lands in the outbox and resolves on reconnect
- A coordinate implausible against recent history is refused as an anchor
- A `venue_claim` never appears in another traveller's recommendations
- Promotion fires exactly when its evidence threshold is met, and not before

## Acceptance

- [ ] `venue_claim` tier exists, promotion criteria encoded as data
- [ ] Coordinate cross-check against OSM and Wikidata before any persistence
- [ ] Identity resolution through `venue_external_id`
- [ ] Runtime path shares the loader's guards, proven by a test that trips one
- [ ] All model output persisted as `attribute_claim` per SPEC-17
- [ ] Unknown-place response invites contribution rather than guessing
- [ ] Cache and circuit breaker cover the flow; per-traveller budget enforced
- [ ] Offline path queues and resolves, never fabricates
- [ ] Suite green (R8); verified from `origin/main` (R10)
