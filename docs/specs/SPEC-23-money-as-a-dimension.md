# SPEC-23: Money as a First-Class Dimension

> Status: SPECIFIED. Not implemented.
>
> Depends on SPEC-13 for the region-level anchors (`currency`,
> `typical_meal_cost_band`, `fare_band_base`, `fare_per_km`, `tipping_norm`), on
> SPEC-16 for edges to hang transport cost on, and on SPEC-17 for the claim and
> provenance model that every amount travels under.
>
> This is the engineering contract that makes VISION section 20 buildable. That
> section describes what cost intelligence should feel like; nothing here changes
> its ambition, and everything here is about the representation it needs and does
> not have.

## Goal

Make "can this traveller afford this, here" and "what will today cost" questions
the system can answer, rather than questions it currently has no vocabulary for.

## Why this is worth doing now

Three arguments, and only the second is about the survey.

**The data layer's money representation is its weakest part, measurably.** A venue
carries one unconstrained text band and nothing else. `venues_rag.price_band` was
added by migration 0011 as bare `TEXT` with no CHECK, while `venue_dish.price_band`
has one and `taxonomy_term` holds the vocabulary -- the third instance of the
drift class we have now fixed twice. There is no venue-level amount at all, so an
entry fee has nowhere to go. `currency_code` exists on `venue_dish` only, which
means the one table that can express an amount is also the only one that knows
what currency it is in. The scheduler contains no reference to price, cost, budget
or fare: it is entirely money-blind. And nothing in the traveller or party model
expresses spend capacity, so even with perfect venue prices there is nothing to
rank affordability against.

**It is the strongest signal the research produced.** Cost was picked in the top
three factors by nearly every short-form respondent, the highest count of any
answer on either instrument, and it appeared unprompted in what people wanted a
local friend to tell them. See `docs/research/SURVEY_FINDINGS.md`, including its
warnings about the sample.

That evidence needs a caveat this spec should state rather than bury. It is a
*stated* preference collected by a ranking question, which is the kind of data
this product's whole thesis distrusts, and "cost matters to me" is a cheap answer
to give. Decision 6 below is the resolution: a budget is a constraint rather than
a taste, and people misreport tastes while knowing their constraints. But the
reason to act is that the survey and a known structural gap point at the same
place, not the survey by itself.

**A band that is not anchored to a region cannot transfer between cities**, and
cross-city transfer of a traveller's taste is the core product claim. Roadmap
concern 6 names `price_band` as one of the few carriers of that transfer. Today
`budget` in Luang Prabang and `budget` in Dubai are the same string and wildly
different amounts, so the carrier silently means nothing the moment a second
region exists.

## Design decisions

1. **A band and an amount are different things and the model needs both.** The
   band is an ordinal for ranking within a region and survives having no data. An
   amount with a currency is what a day total requires. Keep both, and never
   derive one from the other silently: a band inferred from an amount must record
   that it was inferred, and an amount must never be invented from a band.

2. **An amount without a currency is not storable.** The rule migration 0015 wrote
   for `venue_dish` -- integer minor units per the ISO 4217 exponent -- becomes
   the rule everywhere, enforced rather than documented. Every table that holds an
   amount holds its currency code beside it, and a write with one and not the
   other fails. This is where the suspected AED magnitude bug lives, and the
   reason it is only *suspected* after months is that nothing has ever been able
   to check.

3. **A band is meaningless until anchored to a region.** SPEC-13's
   `typical_meal_cost_band` is the anchor that gives `budget` an amount in a given
   place. Band-to-amount resolution is per region and refuses rather than guesses
   for an unregistered region, exactly as SPEC-13's fare band does. This is what
   makes a traveller's price tolerance portable: tolerance is stored as a position
   relative to local normal, not as a number.

4. **`venues_rag.price_band` gets the same constraint every other taxonomy term
   has.** It is validated against `taxonomy_term` like `vibe_tags` and `audience`,
   which closes the third occurrence of a defect class we have twice declared
   closed.

5. **Cost is experienced per day, not per venue.** The number a traveller cares
   about is the day: entries, meals, transport between activities, tips. Transport
   cost belongs on `trip_edge` alongside `observed_duration_minutes`, because it is
   a property of the movement and not of either endpoint. It also inherits that
   column's unsolved problem -- a real fare is only known after the fact, so the
   estimate and the observation are two fields, not one, and the observation needs
   a writer on sync or it stays empty exactly like duration has.

6. **Budget is revealed, not stated.** Do not ask a traveller for a daily number:
   they will answer badly, and the answer will be wrong by the third day. Repeated
   rejection of splurge suggestions, taking the cheaper of two offered options,
   and dwell at free venues all reveal tolerance, which is SPEC-11's forced-choice
   logic applied to price and consistent with every other preference in this
   system. One exception, and it is a constraint rather than a preference: if a
   traveller volunteers a hard daily cap, it is honoured exactly and never
   softened, because a cap that is quietly treated as a suggestion is worse than
   no cap.

7. **Every amount is a claim under SPEC-17, with a short horizon.** A price read
   off a menu by a traveller standing there, a price from an official listing, and
   a price a model produced are not interchangeable, and prices go stale faster
   than almost anything else we store. So amounts enter `attribute_claim` with
   provenance, their registry horizon is measured in weeks rather than months, and
   past that horizon the amount degrades to its band rather than continuing to
   present as current. A stale amount shown confidently is the single most
   damaging thing in this spec, because it is checkable by the traveller at the
   till and being caught wrong about money costs more trust than being vague.

8. **A day estimate is always a hedge, never a quote.** Under SPEC-22 decision 2
   that means the qualifier sits inside the sentence. There is no rendering of a
   day total as a bare number, because a bare number reads as a promise and this
   one is a sum of estimates with a stale component.

9. **`free` is a value; NULL is ignorance.** `free` is already in the
   `price_band` taxonomy and must never be represented as a missing price. The
   distinction matters more than it looks: free venues are the lever a budget-
   constrained day is rebalanced with, and collapsing them into unknown makes the
   cheapest useful recommendation invisible. Three of the curated Luang Prabang
   venues are already banded `free`.

10. **No conversion at display time without a cached rate and its timestamp.**
    Converting with a stale rate produces a confidently wrong number, which is
    decision 7's failure in a different costume. Amounts are shown in local
    currency with the traveller's currency as the hedged secondary, never the
    reverse, and if there is no rate with a timestamp there is no conversion.

## Not in scope

Taking payments, affiliate revenue, subscription pricing, dynamic or predicted
pricing, and the choice of exchange-rate provider. Venue-level accepted payment
methods belong to SPEC-17's attribute registry, and region-level payment norms
including UPI acceptance belong to SPEC-13; neither is re-specified here, and the
two must not become a third registry.

## Shape

Sketched rather than settled, and no migration number is claimed here: numbers are
taken at implementation time.

    venues_rag       entry_amount_minor, entry_currency_code, price_band (constrained)
    trip_edge        transport_cost_estimate_minor, transport_cost_observed_minor,
                     transport_currency_code
    region           currency, typical_meal_cost_band, fare_band_base, fare_per_km
                     (SPEC-13, unchanged)
    traveller        revealed price tolerance as a band position, plus an optional
                     hard daily cap
    attribute_registry  amount attributes at a weeks-scale horizon (SPEC-17)

## Tests

- An amount written without a currency code is rejected, asserted on the
  production write path rather than on a helper the test calls itself
- Band-to-amount resolution returns different amounts for Luang Prabang and Dubai,
  and refuses for an unregistered region
- A `venues_rag.price_band` value outside `taxonomy_term` is rejected
- `free` and NULL are distinguishable end to end, and a free venue is reachable by
  a query for the cheapest option
- An amount past its staleness horizon renders as a band, not as a number
- A day total renders hedged; a test fails on a bare numeric total
- A volunteered hard cap is never exceeded by a generated day, including after a
  reroute
- Revealed tolerance moves in response to rejections, and no code path asks the
  traveller for a number
- No conversion occurs when the cached rate has no timestamp
- An observed transport cost is written from sync rather than left NULL, which is
  the SPEC-16 lesson applied before it repeats

## Acceptance

- [ ] Currency travels with every amount, enforced on write
- [ ] `venues_rag.price_band` constrained against `taxonomy_term`
- [ ] Band-to-amount resolution per region, refusing for unregistered regions
- [ ] Transport cost on `trip_edge`, estimate and observation as separate fields,
      with a writer for the observation
- [ ] Day total computed and rendered as a hedge
- [ ] Revealed price tolerance derived from signals; hard cap honoured exactly
- [ ] Amounts stored as SPEC-17 claims with a weeks-scale horizon
- [ ] Suite green (R8); verified from `origin/main` (R10)
