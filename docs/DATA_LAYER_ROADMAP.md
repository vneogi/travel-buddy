# Data Layer Roadmap

> Extends `docs/VISION.md` and `docs/MARKET_STRATEGY.md`. The technical
> specification is `MASTER_BRD.md`; this document says what the data layer needs
> to become and in what order, not how the system works today.
>
> Current state and risks: `docs/PROJECT_STATUS.md`.

## Why this document exists

Three objectives set the direction:

1. The app must be globally scalable, so the plumbing goes in now and no massive
   rework is required later.
2. Next-generation capability must be supportable -- graph databases, agent
   memory, low-cost and open-source models -- with the backend swappable.
3. The experience must be frictionless, which constrains what the data layer has
   to be able to answer without a network round trip.

Everything below is ordered by cost of delay, not by how interesting it is. An
item near the top is there because it gets materially more expensive with every
week of accumulated data, not because it is more valuable in the abstract.

## What the Laos verification taught us, and why it drives this

Two findings from G3e generalise well beyond names.

**Model-generated venue data is wrong at a rate we cannot currently measure.**
Of the ten Lao names that could be checked against an external source, five were
wrong. The other 48 cannot be checked at all. Those names were produced by the
same process, in the same pass, as `vibe_tags`, `audience`, `price_band` and
`typical_dwell_minutes` -- none of which carry any provenance, and all of which
feed the taxonomy we have been calling the moat. We have no basis for believing
the attributes are better than the names. We only lack the means to check them.

**The verifiable set and the differentiated set are close to disjoint.** Open
datasets carry temples, malls, transport hubs and chains. They do not carry the
neighbourhood restaurant that makes a recommendation worth having, and that is
true in Bangkok as much as in Vientiane -- the corridor cities improve landmark
coverage enormously and barely move the long tail. If Wikidata has a place, so
does every competitor. So field verification by a traveller standing in front of
a venue is not a stopgap for an unpopular destination; it is the only mechanism
that will ever produce trustworthy data for the places that differentiate us.

Both findings point the same way: the data layer needs to record where every
fact came from and how much to trust it, and it needs somewhere to put facts
that were computed rather than curated.

## The seven concerns, in order

### 1. The itinerary is an opaque blob -- SPEC-16

`trip_states.state_json` holds the entire itinerary: every node, time, lock and
venue reference. Nothing about itinerary behaviour is queryable, joinable or
computable without parsing JSON in application code.

For a product whose thesis is learning from what travellers do to their
itineraries, an unqueryable itinerary is a structural contradiction. Concretely,
it blocks:

- every batch job in concern 4, because they need to join signals to itinerary
  position
- transitions as first-class objects, which is where the convenience layer lives,
  because an edge cannot exist inside a blob
- any graph-database story, because the edges are exactly what a graph needs and
  they are currently implicit
- asking which venues co-occur, which is the first question any recommender will
  ever ask

**This also makes booking anchors smaller rather than larger.** SPEC-10 is
currently scoped as adding booking fields to a TripNode that lives in the blob.
Once nodes are rows, a booking anchor is a node with a type and `is_locked` set,
which is most of the feature. Building SPEC-10 against the blob first means
building booking anchors twice.

The change is safer than it sounds, because storage can be normalised without
changing the wire format: the API composes nodes and edges back into the shape
the Flutter app already consumes. That makes it a server-side change with no app
release, no client migration and no new offline-cache format. See SPEC-16.

Cost of delay: the backfill has to parse every existing `state_json`. Today that
is a handful of trips belonging to one user. After the Oct 2 field test it is
real data that matters, and after the first cohort of testers it is a project.

### 2. Venues have no external identity

`venues_rag` records no `wikidata_qid`, no OSM id, no Google place id. Three
consequences:

- ingesting a second city from multiple sources produces duplicates that cannot
  be reconciled, because there is no key to reconcile on
- a venue can never be refreshed or re-verified against its source, so the
  verification I ran for Laos cannot be re-run incrementally or extended to a
  new city without redoing the matching by hand
- the same venue appearing in a curated file and in an OSM extract is
  indistinguishable from two different venues

Model this as a table rather than columns, because one venue legitimately has
several external identities and each carries its own confidence and its own last
verified date:

    venue_external_id(venue_id, source, external_id, confidence, verified_at)

This is the same shape `data/laos_name_verification.json` already produces, so
the first population of it is a load rather than a research task.

Cost of delay: near zero to add now, a deduplication project once a second city
is ingested. This is the cheapest item on the list and it is the one that
directly enables adding cities on demand.

### 3. Provenance exists only on names

SPEC-12 gives `names_local` a `source` per entry. Nothing else has it. Extend
the pattern to curated attributes, per value rather than per venue, because
`vibe_tags` is an array and the provenance of one tag says nothing about the
next:

    venue_attribute_source(venue_id, attribute, value, source, confidence, set_at)

The closed source vocabulary from SPEC-12 applies unchanged, `field_verified`
included. This does not restructure `venues_rag`; it records alongside it.

Cost of delay: grows with every venue tagged, and it is unrecoverable in
retrospect. Once a tag has been in the database for six months, nobody can
reconstruct whether a human chose it or a model guessed it.

### 4. There is nowhere for computed facts to live

Every fact in the schema is either raw capture (`signal`) or hand-curated
(`venues_rag`). There is no layer for facts derived from behaviour, which is
where both classic machine learning and agent memory have to live.

    derived_feature(subject_type, subject_id, feature_key, value, computed_at,
                    method_version, sample_size, confidence)

Four rules make it safe:

1. **Derived never overwrites curated in place.** Resolution happens at read
   time, so a computed value can always be compared with the curated one it
   disagrees with. Overwriting would destroy exactly the audit trail concern 3
   exists to create.
2. **Everything is recomputable.** `method_version` and an append-only signal
   log mean a fixed bug can be applied retroactively.
3. **`sample_size` gates influence.** A feature computed from two visits does
   not get to move the scheduler. A stated minimum per feature, enforced at read
   time.
4. **The same table serves agent memory.** A user-subject feature is the same
   shape as a venue-subject one. Building this once satisfies both objective 2
   and any future model.

### 5. Edges are implicit

Covered structurally by SPEC-16, called out separately because it is a product
concern and not only a schema one. The friction between two activities -- the
exit, the transport mode, the fare, the wait -- is where convenience is won, and
it is currently nowhere in the data model. A first-class edge is also precisely
what a graph backend would consume, which makes objective 2 a consequence of
this work rather than a separate project.

### 6. The taxonomy is unversioned

`vibe_tags`, `audience`, `price_band`, dwell bands and cuisine are the only
things that carry a traveller's taste from a city they have visited to a city
with no venues in common. That transfer layer is the core of the product's
cross-city claim, and it is an unversioned list of bare strings that was
silently reverted once by merge `c5f64f3` without any test noticing.

    taxonomy_term(taxonomy, term, introduced_in, deprecated_in, replaced_by, notes)

The loader validates against it, so a rename becomes a data migration with a
recorded replacement rather than an edit to a constant that silently orphans
every venue already tagged.

Cost of delay: proportional to the number of venues tagged, which is
proportional to the number of cities. Cheapest before the second city, not after.

### 7. Money is barely represented -- SPEC-23

Added after the survey, though it does not rest on the survey. A venue carries one
unconstrained text band: `venues_rag.price_band` was added by 0011 as bare `TEXT`
with no CHECK, while `venue_dish.price_band` has one and `taxonomy_term` holds the
vocabulary, which is the same drift class as concerns 2 and 6 in a third place.
There is no venue-level amount, so an entry fee has nowhere to live.
`currency_code` sits on `venue_dish` alone. The scheduler mentions no price, cost,
budget or fare anywhere, and the traveller model has no notion of spend capacity,
so affordability is not a thing this system can currently rank on.

Two consequences beyond the obvious one. A band that is not anchored to a region is
not a transfer carrier at all, which undercuts concern 6: `budget` is the same
string in Luang Prabang and Dubai and a different amount, so a tolerance learned
in one city means nothing in the next. And transport cost is a property of an
edge, so concern 5 is where it belongs, inheriting the writer problem that
`observed_duration_minutes` still has.

    venues_rag  entry_amount_minor, entry_currency_code, constrained price_band
    trip_edge   transport_cost_estimate_minor, transport_cost_observed_minor

Cost of delay: it compounds with venues, cities and trips at once, which is worse
than any other concern here. Every venue curated without an amount is a venue to
revisit, every region added without an anchor makes the band less meaningful, and
every trip taken without transport cost on the edge is observation lost for good.
Not the most urgent, because nothing is broken today and the field test does not
need it, but the cheapest moment to add the columns is before the second city.

## Position on machine learning

**No recommender, and not because of engineering cost.** Collaborative filtering
-- people who did this also did that -- needs overlap between users and items. At
one user and 74 venues there is no overlap to find; this is arithmetic, not
modelling. Meaningful item-to-item co-occurrence needs users in the thousands
per city, and until then content-based retrieval over the taxonomy strictly
dominates it. That is what `hybrid_venue_search` already does, and the LLM
supplies the reasoning on top. Adding a recommender now would be building a
model with no data to fit.

**Batch compute, yes, and from the first trip.** The distinction that makes this
work at our scale: personalisation needs many users, but data correction needs
only many visits. Aggregating behaviour per venue is useful with a single
traveller and improves monotonically:

| Job | Input | Corrects |
|-----|-------|----------|
| Observed dwell | visited_confirmed against the next node's start | `typical_dwell_minutes`, which is currently a model's guess |
| Lateness contribution | arrival_delta by venue | scheduler buffers for venues that always overrun |
| Rejection rate | reroute_rejected by venue | `trap_score`, a column that already exists and nothing populates |
| Dish frequency | dish_ordered by venue_dish | the glossary, and which dishes are actually available |

Each writes to `derived_feature` with its `sample_size`, and none of them is
allowed to influence the scheduler below a stated threshold. This is a real
machine-learning capability, it compounds from trip one, and it is more
defensible than collaborative filtering ever is, because it improves the
underlying data rather than ranking over data of unknown quality.

**What this leaves open for later, deliberately.** A recommender, sequence
mining over itineraries, and embedding-based user vectors all become possible
without rework once `derived_feature` exists and nodes are rows. That is the
whole point of doing the plumbing first: the model is the cheap part, and the
schema it needs is the expensive part.

## A process defect the reprioritisation just created

Specs currently pre-allocate migration numbers: `0012` for SPEC-10, `0013` for
SPEC-11, `0014` for SPEC-12, `0015` for SPEC-13, `0016` for SPEC-14, `0017` for
SPEC-15. That was harmless while build order matched spec order. It stops being
harmless the moment they diverge, which is exactly what putting SPEC-16 ahead of
SPEC-13 does.

Migrations must apply in numeric order. Spec numbers are identifiers and carry
no priority. Reserving a migration number in an unbuilt spec therefore asserts a
build order that nobody has committed to.

**Rule going forward:** a migration takes the next free number at implementation
time, not at specification time. Specs describe the schema change and do not name
the file. The existing pre-allocations stay where a spec is genuinely next in
line and are treated as advisory everywhere else.

## Sequencing against the Oct 2 field test

The field test proves engine behaviour -- rerouting, the offline write path,
signal capture. It does not require complete or verified data, which means Laos
data quality is no longer worth spending on beyond the deterministic corrections
already identified.

That frees the window before Oct 2 for exactly this work, with one constraint:
nothing that risks the itinerary core should land in the last weeks before a
trip depends on it. SPEC-16 is therefore either early or after, not adjacent.

Suggested order:

1. Deterministic Lao token corrections and the script guard. Small, closes a
   known defect, no network.
2. `venue_external_id` and `taxonomy_term`. Additive, cheap, independent of
   everything else, and they unblock adding a city on demand.
3. SPEC-16 itinerary normalisation, storage only, wire format unchanged.
4. SPEC-10 booking anchors on the normalised schema, where an anchor is a locked
   node.
5. `venue_attribute_source` and `derived_feature`, then the first two batch jobs.
6. SPEC-13, SPEC-14 and SPEC-15, which all become simpler once regions, edges
   and provenance exist.

The halal and pork safety hole is not in this list because it is not a schema
concern and should not wait for one.

## Not decided

- Whether a graph database is adopted at all, or whether explicit edges in
  PostgreSQL are sufficient indefinitely. This roadmap makes the choice possible
  and does not make it.
- Which model provider serves which task once open-weight models are viable.
  `services/llm_service.py` already isolates this behind one gateway.
- Whether `derived_feature` stays in PostgreSQL or moves to a dedicated store
  once volume justifies it. The read-time resolution rule means callers do not
  need to know.
- Whether attribute provenance is backfilled for the existing 74 venues or only
  recorded going forward. Backfilling means asserting a source for tags nobody
  can now trace, which may be worse than admitting they are unknown.
