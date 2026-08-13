# SPEC-14: Dietary model -- decision record

> Status: DECIDED, DESCOPED. This is not a feature specification. It records why
> the app makes no dietary suitability claim, and what would have to change for
> that to be revisited.
>
> Supersedes the earlier version of this spec, which specified dietary
> constraints as a hard safety filter. Nothing from it is scheduled.

## The decision

The app does not tell a traveller whether a venue suits their dietary
constraint. It carries ingredient facts where it has them, presented as facts
about a dish rather than as a judgement about a kitchen, with a disclaimer. It
makes no halal, Jain, vegetarian or pure-veg claim, and it does not filter on
one.

## Why the earlier version was wrong

Not wrong about the importance. Wrong about whether we can deliver it.

That version opened with two facts. Halal is not enforced against pork in the
current checker. And the constraints that matter most to this corridor's
traveller -- Jain, no onion or garlic, pure vegetarian with kitchen separation --
are not representable at all. Both are true, and the conclusion drawn was to
build a richer constraint model and enforce it as a filter.

The step never checked was whether anything could populate it. Measured: in
OpenStreetMap, `diet:halal` is tagged on 20 of 6611 central Bangkok points of
interest. `diet:vegetarian` reaches about two percent. Dubai, the best case in
the corridor, manages six and seven percent. Kitchen separation is not a tag that
exists anywhere.

So the choice was never between a weak dietary filter and a strong one. It was
between making no claim and making one that rests on a model's guess. A dietary
claim from a guess is worse than silence, because a traveller who is told a
kitchen is halal stops checking. That converts their caution into our
confidence, which is the one trade this product must never make.

The hole only exists if the app makes the claim. Retiring the claim closes it.

## Decisions

1. **`suitable_for` is retired as a claim.** No dietary badge, no dietary filter,
   no dietary ranking adjustment. Whatever code path presents or filters on it
   comes out.

2. **Ingredient facts stay, as facts.** `contains` and `may_contain` on a dish
   are useful and often verifiable from a menu. They stay, described as what a
   dish is made of, never as what a person can safely eat. They are
   informational and must never act as a silent filter. A traveller who reads an
   ingredient list is making their own decision, which is exactly the point.

3. **The halal-versus-pork defect closes by retirement, not by a rule.** Adding
   the missing `LABEL_EXCLUDES_ALLERGENS` entry would make a wrong answer look
   considered: it fixes a symptom in a system whose input cannot support its
   output. Remove the claim instead, then update the severity entry that records
   the defect. Until the retirement lands the defect is live, so it stays on the
   risk register.

4. **A disclaimer ships with every food recommendation and every driver card.**
   Dish data is partly model-generated, menus change, and no kitchen here is
   audited. The disclaimer belongs at the point of the recommendation, not in
   terms of service. This decision survives from the earlier version unchanged.

5. **Under SPEC-17, dietary attributes sit on the safety list.** They can only be
   asserted from an official source, deferred, or refused outright -- never
   asserted from extraction or from generation. This spec is the reason that list
   exists, and the list is what stops the claim being reintroduced quietly by a
   later feature.

6. **Named conditions for reopening.** Operator self-certification with an audit
   trail, or a licensed certification dataset with real corridor coverage. Model
   inference over menus and reviews does not qualify at any confidence, and
   neither does a lone OSM tag. If either arrives this becomes a feature spec
   again, and the constraint-versus-preference distinction from the earlier
   version is the right starting point: rank on preferences, filter on
   constraints.

7. **The dish-glossary safety gaps are a data quality item, not a dietary
   feature.** Three of four dishes marked hot carry no moderating phrase, and the
   raw-meat laap has no phrase for asking that it be cooked. Those are missing
   phrases in the glossary and belong with the Lao curation work. Retiring the
   dietary claim does not retire them.

## What this changes in the repo

- The `suitable_for` presentation and filtering paths are removed
- `VALID_DISH_CONTAINS` still belongs in `config/dietary.py` rather than in the
  glossary loader; that relocation stands on its own merits (R5)
- The severity entry recording the halal defect is updated when the retirement
  lands, not before
- No migration. Nothing here adds a column

## Tests

- No API response carries a dietary suitability claim for a venue
- A request expressing a dietary constraint does not silently filter the
  candidate set
- Ingredient facts are returned with their disclaimer
- A dish with no ingredient data returns absent rather than an empty list, since
  an empty list reads as nothing-to-worry-about
- A food recommendation and a driver card each carry the disclaimer

## Acceptance

- [ ] `suitable_for` no longer presented or filtered on anywhere
- [ ] Ingredient facts retained, labelled as ingredients, never acting as a filter
- [ ] Disclaimer on food recommendations and on driver cards
- [ ] Dietary attributes on the SPEC-17 safety list
- [ ] Risk register entry for halal-versus-pork closed by retirement, with the
      reason recorded
- [ ] Suite green (R8); verified from `origin/main` (R10)
