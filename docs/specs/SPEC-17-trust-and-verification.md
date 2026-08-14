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

14. **Confirmation decays; it does not last forever.** Every claim carries
    `observed_at`, and every attribute declares a staleness horizon in the
    attribute registry. Past its horizon a claim degrades by one tier -- `assert`
    becomes `hedge`, `hedge` becomes `ask` -- rather than vanishing, because a
    year-old confirmed name is still the best thing we have while a year-old
    "closed on Mondays" is not. Horizons differ by attribute class, and identity
    outlives operations by years: a name or a coordinate is stable, whether a
    place still exists is a question of months, and anything about hours is weeks
    and deferred anyway. Re-confirmation appends a new claim and resets freshness;
    it never mutates the old one, or we lose the history that makes contributor
    weight computable. Question card routing (decision 11) should prefer
    attributes at or past their horizon, which produces a resurvey cadence for
    free and stops us asking a traveller to re-verify what someone confirmed last
    week.

    Every Door, an OpenStreetMap survey app, expires a confirmation after two
    months and then offers the place for resurvey again. Without a rule of this
    kind the `field_verified` tier fills up with stale facts that still present
    as authoritative, which is the failure this spec exists to prevent arriving
    by a slower route.

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

The attribute registry is data, not code, and decisions 7, 8, 10 and 14 all read
from it rather than each carrying their own list:

    attribute_registry(
      attribute, attribute_class, staleness_horizon_days,
      is_safety_relevant, needed_at_arrival, deferral_target NULL
    )

An attribute with no registry entry cannot be displayed at all. That is the
mechanism which forces a new field to be given a horizon and a safety judgement
before it can reach a screen, rather than inheriting a permissive default because
nobody thought about it.

The registry also settles a case the tiers alone get wrong. Whether a venue takes
only cash is a commodity fact, and decision 8 would ordinarily defer a commodity
fact to Maps. But it is needed at exactly the moment there is no connection to
defer over: at the counter, wallet already out. So its `deferral_target` is null
and `needed_at_arrival` is true, which forces it into the cached set instead of
the deferred set:

    payment_methods, operational, 180, false, true, NULL

That combination -- commodity, yet not deferrable -- is the useful distinction
here, and it is worth stating because the naive reading of decision 8 sends
exactly the wrong field to Maps. What makes something deferrable is not that
Google has it; it is that Google has it *and* we will have a connection when the
question is asked.

The evidence for prioritising this one is thin but it is the only direct evidence
we hold about the disconnected moment. Asked what they struggled with most in an
unfamiliar place with no internet, most respondents named making a payment, ahead
of navigation and ahead of anything about the schedule. Small sample and a weak
instrument, recorded in `docs/research/SURVEY_FINDINGS.md`. Cash-only is also the
cheapest field confirmation in the registry: it is printed at the till, it is one
tap, and it changes often enough to be worth re-asking.

## Prior art

Three open-source apps have already solved parts of this and are worth reading
before implementing. Two are GPL-3.0, so the ideas can be taken and the code
cannot -- a copied widget would relicense our client, which is a real constraint
rather than a formality.

- **Every Door** (GPL-3.0) treats confirmation as an action distinct from editing
  and expires it after two months. It is the source of decision 14, and evidence
  that a one-tap confirm works for people doing this in the street.
- **OpenStop** (GPL-3.0) defines its entire question catalogue as data, at
  `assets/advanced_question_catalog/definition.json` with per-question localised
  strings alongside. Adding a question is a data change, not a release. Our
  question cards should take that shape, versioned the way `taxonomy_term` is.
- **Open Food Facts** (Apache-2.0, so reusable) is the closest analogue to this
  whole spec in another domain: crowdsourced facts with per-field provenance,
  photo evidence attached to claims, a completeness score that makes confidence
  visible, and full revision history so a bad edit is attributable rather than
  destructive. Their photo capture-and-upload pipeline is worth reusing outright,
  because compression, retry over a poor connection and crop guidance are exactly
  what will be quietly broken in our first attempt at asking somebody to
  photograph a sign.

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
- A claim past its attribute's staleness horizon does not resolve to `assert`
- Re-confirmation appends a claim and restores the tier, and the superseded claim
  is still present afterwards
- An attribute with no registry entry is refused rather than displayed with a
  default horizon
- Question card selection prefers an important stale attribute over a fresh one

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
- [ ] Attribute registry exists as data, carrying a staleness horizon and a safety
      flag per attribute; an unregistered attribute cannot be displayed
- [ ] Staleness degrades the tier by one step, with a test per attribute class
- [ ] Suite green (R8); verified from `origin/main` (R10)
