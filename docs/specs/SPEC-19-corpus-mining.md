# SPEC-19: Corpus Mining for Operational Knowledge

> Status: SPECIFIED. Not implemented. Depends on SPEC-17.
>
> No migration number is claimed. Numbers are taken at implementation time.

## Goal

Extract the practical knowledge that unstructured travel text carries and no
structured dataset does. "When the tour ends, leave by gate 16 -- it puts you
straight on the metro." "Everyone orders the same dish here." "Do not come
mid-afternoon in August." Turn that into claims the itinerary engine can act on.

## Why this is the missing input, not a new pillar

Each of those examples fills a hole we already had. Gate 16 is a property of the
transition between two places, and SPEC-16's `trip_edge` had no data source
planned at all -- the convenience layer was going to wait months for our own
travellers to generate it. The dish everyone orders is `venue_dish.is_signature`
with evidence behind it instead of a curator's opinion. The August advisory is a
time-and-season qualifier that nothing in the schema currently models.

So this is the supply for three commitments already made.

## Design decisions

1. **Mine only what the authoritative sources do not structure.** In scope: exit,
   entrance and transfer advice; the dish repeatedly named; time-of-day and
   seasonal advisories; queue, ticket and timing mechanics; dress and conduct
   requirements; local overcharging and scam patterns. Out of scope: opening
   hours, ratings, photographs, phone numbers -- SPEC-17 defers those to the
   authoritative source, so extracting them is wasted work with a licensing risk
   attached.

2. **Only openly licensed corpora. This is a legal gate, not a difficulty
   ranking.** Wikivoyage is the primary source and an underrated one: CC BY-SA
   licensed and written as practical advice, so its "get in", "get around" and
   "eat" sections are exactly this genre. Wikipedia and OSM descriptions add some.
   An openly licensed places dataset may be used once its licence has been read
   rather than assumed. First-party content -- our own travellers' notes and
   answers -- has no ceiling and is the part that compounds.

   Google and TripAdvisor are excluded. Their terms restrict storing review
   content and deriving datasets from it, and scraping the pages breaches the site
   terms outright. Excluded on licensing, not on difficulty, and to be revisited
   only with legal input.

3. **CC BY-SA carries obligations.** Attribution and share-alike apply to derived
   text. Store the corpus reference with every claim and surface attribution
   wherever extracted prose is shown. Prefer extracting a *structured fact* over
   copying a sentence: it reduces the obligation and improves the data.

4. **No claim without a citation.** Every extraction records the corpus, a stable
   reference, and the span it came from. An extraction that cannot cite is
   discarded, not downgraded. This is what makes a claim auditable when a
   traveller reports it was wrong.

5. **Durable knowledge about a place pair is not a trip edge.** "Gate 16 reaches
   the metro" is true independent of anyone's itinerary. It attaches to the pair
   of places, per SPEC-16 decision 9, and a trip edge references it. Storing it on
   a trip edge would relearn it for every traveller.

6. **Time and season qualifiers are structured, not prose.** A month range, a
   time-of-day window, and a direction: avoid or prefer. "Hot in August" as free
   text cannot be scheduled around; a structured advisory can.

7. **Extraction is batch, off the request path.** It is on nobody's critical path,
   so it can be slow, cheap and re-runnable. Re-running over a fresh corpus dump
   must be idempotent.

8. **Mining generates hypotheses; SPEC-17 resolves them.** An extracted claim
   starts at `review_extraction` with an evidence count. Where it matters and
   stays weak, it becomes a question card for a traveller who is there. That
   handoff is the flywheel: mining without verification industrialises unverified
   claims, and verification without mining has nothing to ask about.

9. **Independence is what makes corroboration mean anything.** Three corpora
   repeating one upstream sentence is one source. Deduplicate on content before
   counting evidence, or confidence inflates itself.

10. **Safety-adjacent categories need a human before they are shown.** Scam
    patterns, conduct requirements and anything on the SPEC-17 safety list are
    reviewed rather than published on extraction confidence alone.

## Tests

- An extraction with no citable reference is discarded
- Out-of-scope attributes such as opening hours are never written as claims
- A corpus outside the allowed licence set is refused by the ingest gate
- Place-pair knowledge attaches to the pair, not to a trip edge, and one trip
  consuming it does not mutate it
- Time and season advisories parse into structured ranges the scheduler can read
- Re-running extraction over the same dump changes nothing
- Near-duplicate claims across corpora collapse to one before evidence counting
- A safety-list category cannot reach a displayable tier without human review
- A weak claim about a high-traffic venue becomes a question card

## Acceptance

- [ ] Licence gate on corpus ingest, allowed set held as data
- [ ] Extraction writes `attribute_claim` rows carrying corpus, reference and span
- [ ] Attribution surfaced wherever extracted prose is displayed
- [ ] Place-pair knowledge modelled separately from trip edges
- [ ] Structured time and season advisories, readable by the scheduler
- [ ] Idempotent re-extraction
- [ ] Content-level deduplication before evidence counting
- [ ] Human review required for the safety list
- [ ] Suite green (R8); verified from `origin/main` (R10)
