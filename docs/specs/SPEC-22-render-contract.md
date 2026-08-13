# SPEC-22: Client Render and Interaction Contract

> Status: SPECIFIED. Not implemented, and it precedes every screen.
>
> Depends on SPEC-17 for the definition of the tiers, but not on SPEC-17 being
> implemented. The envelope shape is already specified, so this can be built as a
> client-side type with a stubbed source while the claim store is still being
> written.
>
> Relationship to `docs/UX_BACKLOG.md`: that file lists what we want to build.
> This one constrains how any of it may be rendered.

## Goal

Turn the trust contract into pixels once, so that five queued specs do not each
invent their own way of showing an uncertain fact.

## Why this comes before the screens

SPEC-12, SPEC-11, SPEC-15, SPEC-17 and SPEC-10 all display facts, and all of them
display facts we are not certain about. Left to themselves, the driver card will
invent an "unconfirmed" treatment, question cards will invent a second one, and
the itinerary will quietly show a generated value as plain text because that was
the path of least resistance on the day. The result is an inconsistent trust
language, which for a product whose pitch is trust is not a cosmetic problem.

The same argument applies to the interruption budget. SPEC-15 and SPEC-17 both
say they draw on a shared budget. Neither owns it. A shared resource with two
claimants and no owner is never built, and both subsystems ship able to interrupt
independently.

## Design decisions

1. **The tier chooses the treatment; the screen does not.** A fact widget accepts
   the SPEC-17 envelope, not a string. There is no constructor that takes a bare
   value, which is the client-side mirror of SPEC-17 decision 2: if a component
   *can* render an unsourced value, one eventually will. Make it a compile error
   rather than a review comment.

2. **Five treatments, defined once:**

   | Tier | Treatment |
   |---|---|
   | `assert` | Plain, unadorned text. Confidence is invisible when it is high |
   | `hedge` | The qualifier sits inside the sentence, not in a badge |
   | `ask` | A question card. The value appears only as part of the question |
   | `defer` | No value, and a labelled link saying where it goes |
   | `refuse` | An explicit "we do not know", never an empty space |

   Two of those need justifying. A badge is ignorable and a hedge inside the
   sentence is not, so "travellers usually say it takes 40 minutes" beats "40
   minutes" with a small grey label. And an empty field reads as a loading state,
   which is why `refuse` must say something rather than show nothing.

3. **Decoration only where confidence is low.** Adorning a certain fact trains
   people to ignore the adornment, which disarms the treatment exactly when it
   matters. `assert` therefore gets nothing at all.

4. **No raw confidence numbers, ever, and no percentages.** 0.72 means nothing to
   a traveller and invites false precision. The tier is the only confidence
   signal the UI carries.

5. **Staleness renders as recency, not as a warning.** Under SPEC-17 decision 14 a
   claim past its horizon has already degraded a tier, so the tier is doing the
   work. Show `as_of` in human terms, "confirmed in March", only where recency
   changes what somebody would do. A staleness icon on every field is noise.

6. **Confirm is one tap and never a form.** SPEC-12's promotion to
   `field_verified`, SPEC-17's question cards, and any later correction flow share
   one affordance. A traveller standing in front of signage has one hand free and
   thirty seconds. Every Door validates this by separating confirm from edit; the
   confirm path must not become the edit path with extra steps.

7. **Offline is a designed state, not an error.** Three states, and the middle one
   is not a failure: live, offline with cached data, and genuinely unavailable.
   The offline state shows what we hold plus when it was cached, and does not
   offer retry as the primary action, because there is nothing to retry. No red,
   no warning iconography. This is the one capability competitors cannot copy, so
   it gets design attention rather than an error banner.

8. **The interruption budget lives here and has exactly one owner.** A single
   service that the UI asks for permission to interrupt, holding a per-day cap, a
   minimum gap between interruptions, and a suppression window after a dismissal.
   Callers receive a decision and cannot bypass it. SPEC-15 and SPEC-17 both go
   through it.

9. **Dismissal is data.** A dismissed question card and a deferred checklist item
   are both signals, per SPEC-15's stated-versus-revealed argument. The render
   layer emits the dismissal rather than swallowing it, which also means the
   budget can learn.

10. **One type scale and one spacing scale, declared as tokens.** The corridor
    traveller skews family and older: `seniors` is set on 40 of the 58 Laos
    venues. Minimum body size and minimum tap target are declared once, and a
    guard fails on a literal font size or padding value outside the token file.
    This repo's habit is to enforce conventions with a test rather than a
    convention, and this is no different.

11. **Native script gets a declared text style, and the font coverage is
    tested.** A font missing Lao or Arabic glyphs renders boxes, and it fails
    silently: nothing throws, the layout is fine, and the driver card becomes
    worthless at precisely the moment it is needed. So the bundled font must be
    asserted to cover every codepoint present in the local-script fields under
    `data/`. The driver-facing side of the card also carries its own minimum size,
    because it is read at arm's length by somebody else.

12. **Localisation from the start, honestly scoped.** Strings live in ARB files
    rather than in widgets, because retrofitting that is expensive and touches
    every screen. English and Hindi first, given the target traveller. This is not
    a promise of full localisation, only a refusal to hardcode.

## Tests

- One golden test per tier, five in total
- A fact widget cannot be constructed without a tier, proven by a negative test
  rather than by inspection
- A `refuse` field renders explicit unknown text, and the test fails on an empty
  or whitespace-only render
- Two subsystems requesting an interruption inside one window produce exactly one
  interruption
- A dismissal emits its signal, asserted on the outbox rather than on a callback
- The offline state renders cached content, carries no error colour, and does not
  place retry as the primary action
- Bundled fonts cover every codepoint appearing in the local-script fields under
  `data/`, walked from the files rather than from a fixed list
- No literal font size or spacing value outside the token file
- `flutter analyze` is clean, and the suite runs on a device or emulator at least
  once before this spec is called done

## Acceptance

- [ ] Fact widget takes the SPEC-17 envelope; no code path accepts a bare value
- [ ] Five tier treatments implemented with golden tests
- [ ] Interruption service owns the budget, and both callers route through it
- [ ] Dismissals emitted as signals
- [ ] Offline state designed and implemented as a state rather than an error
- [ ] Token file for type and spacing, with the no-literals guard
- [ ] Font coverage asserted against the actual data
- [ ] ARB wiring in place with English and Hindi
- [ ] Suite green (R8); `flutter analyze` clean; verified from `origin/main` (R10)
