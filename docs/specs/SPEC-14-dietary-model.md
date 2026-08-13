# SPEC-14: Dietary model

> Status: SPECIFIED. Not implemented. Post-Laos, except the safety fix in
> section "The open safety hole", which is not gated on this spec.
>
> Migration `0016`. Allocation: 0011 venues_rag columns, 0012 booking anchors,
> 0013 preference_choice, 0014 driver_card_shown, 0015 region registry,
> 0016 this.
>
> Driver: `docs/MARKET_STRATEGY.md`. This is the sharpest differentiator for the
> corridor's traveller and simultaneously an open safety hole.

## Goal

Represent the dietary constraints that actually decide where a family eats, and
enforce them as a safety property rather than a ranking preference.

## Why this is a safety spec and not a food feature

Two facts, both already recorded elsewhere in this repo.

**Halal is not enforced against pork in the dietary checker.** `MASTER_BRD.md`
section 10 records this as a high-severity safety defect rather than a missing
feature. It is the clearest possible demonstration that the current model treats
dietary labels as tags to match rather than constraints to enforce.

**The constraints that matter most are not representable at all.** Western
allergy models cover vegan, gluten and nuts adequately. None of them model Jain,
no beef, no onion or garlic, eggless, or pure vegetarian with kitchen separation.
For a large share of the corridor's travellers, those are the constraints that
decide the restaurant, and a constraint the schema cannot express produces a
confident recommendation rather than an error. That is rule R9 in the case where
the consequence is a person eating something they hold sacred.

The distinction that organises the whole spec: **an allergy is a medical hazard,
a religious or ethical constraint is a trust hazard.** Both are absolute from the
user's point of view, and neither is a preference to be traded off against venue
quality. Rank on preferences; filter on constraints.

## The open safety hole

The halal-versus-pork defect should be fixed as a standalone change and must not
wait for this spec. It is a small fix to an existing checker with an obvious
test, and leaving a known safety defect open while a larger model is specified is
the wrong order. This spec then subsumes it.

## Design decisions

1. **Constraints are filters, never score adjustments.** A venue that violates a
   declared constraint is removed from the candidate set, not down-weighted. A
   ranked-down violation still surfaces when the candidate set is thin, which is
   precisely when a tired family is most likely to accept it.

2. **Constraint vocabulary is explicit and closed, and every value is
   documented.** At minimum: `vegetarian`, `pure_veg_separate_kitchen`, `jain`,
   `eggless`, `no_beef`, `no_pork`, `halal`, `no_onion_garlic`, `vegan`, plus
   allergen entries kept distinct from the above. `pure_veg_separate_kitchen` is
   separate from `vegetarian` because a vegetarian dish cooked in a shared
   kitchen satisfies one and not the other, and conflating them is the single
   most likely modelling error here.

3. **Implication rules are data, not code comments.** `jain` implies
   `no_onion_garlic` and `vegetarian`; `halal` implies `no_pork`. Encoding these
   once, as data with a test per rule, is what prevents the current halal defect
   from recurring in a new form.

4. **Constraints live on the party member, not the trip.** Vision section 28
   already places `dietary_constraints` on `party_member`, and a group is
   routinely mixed. The venue filter is the union of every member's constraints,
   which means one Jain member constrains the group's dinner. That is the correct
   behaviour and should be visible in the UI rather than silent, since an
   unexplained absence of options reads as a broken app.

5. **Evidence and confidence are recorded per venue.** A venue is
   `verified_by_operator`, `signal_derived`, or `unverified`. The filter states
   which it is rather than implying certainty. "No pork on the menu we have" is
   not "this kitchen is halal", and presenting the former as the latter is the
   failure mode this field exists to prevent.

6. **Degrade by refusing, with a reason.** When no venue satisfies the
   constraint set, say so and name the binding constraint. Never relax a
   constraint silently to fill a slot. This is R6, and it is the one place in the
   product where an empty result is the correct and trustworthy answer.

7. **A disclaimer ships with every food recommendation and every driver card.**
   Dish and venue data is curated and partly model-generated, menus change, and
   kitchens are not audited. The disclaimer belongs in the UI at the point of
   the recommendation, not buried in terms of service.

## Signals

`dietary_constraint_violated` when a user reports that a recommended venue could
not serve them, with the binding constraint in `value_json`. This is the only
mechanism that will find modelling errors in production, and it feeds the
evidence field in decision 5. Registry entry plus migration `0016` in the same
commit, or the drift guard fails (R5).

## Tests

- Halal filter excludes a pork-serving venue. This is the current defect, so the
  test must be shown failing against the pre-fix checker before it passes.
- Each implication rule has its own test: `jain` excludes onion and garlic;
  `halal` excludes pork
- `pure_veg_separate_kitchen` excludes a vegetarian-friendly venue with a shared
  kitchen, proving the two values are not conflated
- A constraint is never satisfied by ranking: with a violating venue as the only
  candidate, the result is empty rather than the violating venue
- Party union: a single constrained member constrains the whole group's results
- An empty result names the binding constraint, asserted on the returned reason
- Unverified evidence is surfaced as unverified, not as compliance
- `dietary_constraint_violated` present in registry and migration `0016`; drift
  guard green

## Acceptance

- [ ] Halal-versus-pork defect closed independently of this spec, with a
      regression test, and the severity entry in `MASTER_BRD.md` section 10
      updated only after the test passes
- [ ] Constraint vocabulary closed and documented, with the rationale for
      `pure_veg_separate_kitchen` being distinct from `vegetarian`
- [ ] Implication rules encoded as data, one test per rule
- [ ] Constraints filter rather than rank, proven by the thin-candidate-set test
- [ ] Party-level union implemented and visible in the UI
- [ ] Per-venue evidence level recorded and surfaced
- [ ] Empty results name the binding constraint
- [ ] Disclaimer present on food recommendations and driver cards
- [ ] `dietary_constraint_violated` in registry plus migration `0016`; drift
      guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean after Dart writes
