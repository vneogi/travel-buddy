# SPEC-17: Trust and Verification Contract

> Status: SPECIFIED. Not implemented.
>
> This spec constrains SPEC-18, SPEC-19 and SPEC-20. Each of those produces
> unverified assertions at scale; this one governs what may be shown, how, and
> what it takes to promote a claim. Implement it first or the other three
> industrialise the failure the Laos names produced.
>
> No migration number is claimed. Numbers are taken at implementation time.

## Goal

The product's foundation is trust, and its engine is a language model. Those are
in tension by default. This spec resolves the tension with a contract: every
displayed fact carries a known provenance, and the way it is displayed is a
function of that provenance rather than a choice made by whoever built the
screen.

## Why this is not a guideline

A guideline fails at the first deadline. Two things already in this repo prove
the point. The driver card nearly shipped presenting model-invented Lao names as
authoritative, and only a deliberate decision stopped it. The dietary model would
have shown a halal badge with no data source behind it, which is why it was
descoped. In both cases the mechanism that failed was human judgement at render
time. So the contract has to be enforced by the API shape and by tests, not by
reviewers remembering.

## Design decisions

1. **Five responses to a fact, not two.** Every attribute resolves to exactly one
   of these, and the tier travels with the value:

   | Tier | When | How it renders |
   |---|---|---|
   | `assert` | Externally sourced or field-confirmed | Plainly, as fact |
   | `hedge` | Corroborated derivation, several independent sources | "travellers report", "usually" |
   | `ask` | Single source, or model-generated | A question card, never a statement |
   | `defer` | Commodity, current, needs connectivity | A link to the authoritative source |
   | `refuse` | Safety-relevant and unverified | An explicit "we do not know" |

2. **No value crosses the API without its provenance.** The envelope for any
   attribute is `{value, source, confidence, tier, as_of}`. A bare scalar is a
   contract violation. The render layer refuses to display a value whose `source`
   is absent, and a test asserts that refusal. This is the single mechanism that
   makes the rest of the spec hold: if a component *can* display an unsourced
   value, eventually one will.

3. **`attribute_claim` is the claim store, and claims are never overwritten.**
   Competing claims coexist and resolution happens at read time. Overwriting
   destroys the evidence that makes confidence meaningful, and it is exactly how
   a generated value silently replaces a verified one.

4. **Resolution is a pure function.** `resolve(claims) -> (value, tier, source)`
   is deterministic, has no model in the loop, and is tested against fixed claim
   sets. A language model may *produce* a claim; it never *adjudicates* one.

5. **Source ranking is a closed, ordered vocabulary:** `field_verified`,
   `official`, `wikidata`, `osm`, `open_dataset`, `review_extraction`,
   `llm_generated`. `field_verified` outranks Wikidata deliberately -- for a small
   restaurant no open dataset will ever carry the name, and somebody who stood in
   front of the signage is the better authority. A test enforces the closed set.

6. **Confidence is evidence, not self-report.** It is a function of how many
   independent sources agree and how recently. Never ask a model how confident it
   is; a fluent guess and a fact produce the same number.

7. **Safety-relevant attributes can never reach `assert` from a generated or
   extracted source.** The safety list is closed: food ingredients, medical and
   pharmacy availability, water potability, areas to avoid, transport that could
   strand someone at night, and religious or cultural restrictions. For these the
   only available tiers are `assert` from an official source, `defer`, or
   `refuse`. Dietary claims are out of scope entirely -- a wrong halal badge costs
   more than a missing one.

8. **Defer rather than restate, for commodity facts.** Opening hours, phone,
   website, photographs, ratings, whether a place is open right now, and above all
   navigation. We will never match a crowd-maintained hours dataset and we will
   never build turn-by-turn. Deep-linking needs no API key and no stored
   identifier: a maps URL built from a name and a coordinate is enough.
   `venue_external_id` has a `google` slot if stable place identifiers are wanted
   later.

9. **Defer at field level inside a confident answer, never as the answer.** "Wat
   Xieng Thong, about 45 minutes, best light before nine, hours on Maps" is the
   product. "I do not know, check Maps" three times running is a worse Maps. A
   test asserts that a response composed entirely of `defer` fields is not
   returned as a recommendation.

10. **Plan-time facts defer; arrival-time facts degrade.** Offline is the
    criterion. A link is worthless at a temple gate with no data, so anything
    needed at the moment of arrival -- the SPEC-12 driver card being the canonical
    case -- degrades to less information rather than to a link.

11. **Question cards are routed by value, not sprayed.** Priority is uncertainty
    times likely future readership times the traveller's proximity: ask about the
    venue they are standing beside, that we hold a weak claim about, that others
    will visit. Cards draw on the same interruption budget as SPEC-15, so the two
    cannot independently decide to interrupt.

12. **Rewards pay for evidence, not for answers.** A photograph of an
    opening-hours plate is checkable; a tap is not. Credit is granted on
    asynchronous validation of the evidence, never on submission. Corroboration
    beats volume: two independent travellers at different times outrank one person
    ten times. Rate limits are per location and per hour, because nobody verifies
    forty venues in an afternoon. Contributor weight rises when past confirmations
    survive later contradiction, which is itself a derived feature.

13. **Reward value stays below the cost of gaming it.** No single action grants a
    large entitlement. Sustained accurate contribution earns the large rewards; a
    single photograph earns a small increment. Pricing a subscription at one
    photograph invites farming.

## Shape

    attribute_claim(
      claim_id, entity_type, entity_id, attribute,
      value_json, source, confidence, evidence_count,
      evidence_ref NULL, observed_at, contributor_ref NULL,
      superseded_by NULL, created_at
    )

The envelope, returned wherever a fact is exposed:

    { "value": ..., "source": "osm", "confidence": 0.8,
      "tier": "assert", "as_of": "2026-08-13" }

## Tests

- `resolve` is deterministic over a fixed claim set, and reordering the input does
  not change the output
- A claim sourced `llm_generated` never resolves to `assert`
- Every attribute on the safety list resolves only to `assert` from an official
  source, `defer`, or `refuse`
- The API returns no attribute without `source` and `tier`, asserted by walking a
  real response rather than a hand-built one
- The render layer raises rather than displaying a value with a missing source
- A response whose fields are all `defer` is not returned as a recommendation
- An arrival-time attribute never resolves to `defer`
- Question card selection respects the shared interruption budget and the per
  location rate limit
- Reward credit is granted only after evidence validation, proven by a case where
  submission happens and credit does not
- Contributor weight falls when a past confirmation is contradicted
- A `source` outside the closed vocabulary is rejected

## Acceptance

- [ ] `attribute_claim` in both backends, append-only
- [ ] `resolve` implemented, pure, covered by the determinism tests
- [ ] Envelope carries value, source, confidence, tier and as_of everywhere a fact
      is exposed
- [ ] Render layer refuses unsourced values, with a test
- [ ] Safety list encoded as data, not scattered conditionals
- [ ] Deferral builds maps links with no API key and no stored identifier
- [ ] Question cards routed by value and bounded by the shared budget
- [ ] Reward credit gated on asynchronous evidence validation
- [ ] Suite green (R8); verified from `origin/main` (R10)
