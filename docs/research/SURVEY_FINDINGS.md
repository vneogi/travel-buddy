# Survey Findings

## Status: STILL AN INSUFFICIENT SAMPLE -- directional only

Two instruments went out to a friend network. The short form (twelve questions)
came back with eight responses; the deep form (forty-one questions) came back
with five. They are different questionnaires and cannot be pooled. Several
respondents are socially connected and describe the same trips, so the effective
number of independent observations is lower than the response count. The bar set
in the first version of this file, twenty independent respondents before anything
here is treated as validation, has not been met.

What follows is worth reading anyway, for one reason: the useful content is not
confirmation of the plan. It is two places where the plan gets no support at all,
and those are cheap to act on even from a weak sample, because a weak sample that
fails to find a pain you assumed was central is still informative.

## What this contradicts

**The arrival-moment safety layer has no demand signal here.** Asked whether they
had ever felt unsafe or lost and wished for quick local help, every respondent who
answered said no. This was a committed direction. The sample is friends describing
mostly smooth trips, much of it domestic Indian travel, so this is not a test of
arriving somewhere unfamiliar late at night on the corridor. But nobody recognised
it as a pain they had experienced, and a different framing of the same moment did
get answers. Decision taken: keep the capability, lead with the eating decision.
See `docs/MARKET_STRATEGY.md`.

**Mid-trip replanning stress is moderate, not acute.** The stress rating clustered
at the middle of the scale on both forms, with nobody choosing the second-highest
option. Asked to describe a specific time a plan fell apart, the answers included
"hasn't happened" and "no problems we faced trip was very smooth". Replanning is
central to how the product is currently pitched. The honest reading is that it may
be a capability which earns trust in the moment rather than a benefit that
persuades anybody to install anything.

**Our offline work is aimed at pains nobody named.** Asked what they struggled
with most in an unfamiliar place with no internet, respondents named making
payments, more than any other answer, plus reading reviews of a place they had
just come across, interacting with locals, and staying in touch with family. Not
one person named navigation, communicating a destination to a driver, or
rescheduling a day. The offline vault, the driver card and offline reroute all
address the second list.

This is the finding with the most direct consequence, and two changes follow from
it. `payment_methods` enters the SPEC-17 attribute registry as a commodity fact
that is nevertheless not deferrable to Maps, precisely because it is needed when
there is no connection to defer over. And the SPEC-22 offline state must cache the
verdict about a venue, not only the schedule, since judging a place you have just
walked past is an offline need we were not promising to serve.

## What it supports, weakly

Cost was chosen in the top three factors by nearly every short-form respondent,
the highest count of any answer on either form, and appeared verbatim in what
people wanted a local friend to tell them. The deep form put local and authentic
first with cost joint second, so read this as cost being at least co-equal with
authenticity rather than as evidence for a budget product. Either way it sits
awkwardly against a data layer whose only money fields are a coarse price band and
a price with a documented minor-unit ambiguity, and against a scheduler that
optimises time and never money.

Food recurs across unrelated open questions: what a local friend should whisper
each day, the best unplanned moment, what changes most when travelling with
children, and the hardest thing about travelling with children. It is the most
frequently volunteered subject in the free text by a wide margin.

Logistics-handling was the unprompted answer to what people wish somebody else
would take care of, phrased once as "travel itinerary and packing" and once as
"someone else doing all the logistics". Note the packing: SPEC-15 specified the
checklist around items that resolve to a place during a trip, and the volunteered
need is the list before departure.

Google is the most trusted review source, with friends second, which is quiet
support for the SPEC-17 decision to defer commodity facts to Maps. Deferring to
something already central to how people check things reads as sensible rather than
as an admission.

Multi-generation travel was the most-selected party type on the short form, and
the deep form skewed towards solo and families with young children. Consistent
with the seniors skew already present in the curated Laos data.

Distance between spots is bimodal: some respondents rated it maximally important
and others near the bottom. Weak support for the transition-cost work.

## Notes on the instrument

The twelve-question form outperformed the forty-one-question form on completions
despite going to a wider group, and the long form's free text degraded noticeably
towards the end, with several answers not addressing the question asked. If there
is another round, the short form is the better instrument.

Questions that supplied an attractive premise produced worthless answers. Asking
when somebody would want an easily bookable trusted local guide returned
"Always". Only the pick-your-top-three questions and the specific behavioural
questions, of which "what do you do when hungry in an unfamiliar area" was the
best, produced anything usable.

## What to do

The highest-value asset in this dataset is the set of respondents who agreed to a
short call. Four questions worth asking them, each aimed at a behaviour rather
than a preference: what did you actually do the last time you could not pay for
something; what would have changed your mind about the chain restaurant; talk me
through the last time you had two unplanned hours; and what did the guide do that
was worth the money.

Until there are twenty independent respondents, cite this file as an insufficient
sample. It has been sufficient to withdraw one framing, redirect the offline
cache, and specify SPEC-23. That last one deserves its reasoning stated, because
it looks like the exception: the cost finding is a stated preference from a
ranking question, which is the kind of data this product's thesis distrusts, and
"cost matters" is a cheap answer to give. What justified acting was not the count
but the coincidence -- the survey pointed at the part of the data layer that was
already the weakest, where venue price is one unconstrained band, currency lives
on one table, and the scheduler has no concept of money at all. A weak signal
aimed at a known gap is worth more than a strong signal aimed at nothing.

Nothing here is sufficient to justify building on its own.
