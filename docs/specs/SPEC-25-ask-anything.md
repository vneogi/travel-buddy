# SPEC-25: The Ask Anything Surface

> Status: SPECIFIED. Not implemented.
>
> Depends on SPEC-17 for the response envelope, SPEC-18 for the discovery path,
> and SPEC-22 for how any of it is rendered. It does not depend on SPEC-18 being
> finished: the intent router can return a refusal for the discovery intent and
> still be correct.

## Goal

One way in for a free-text question, from anywhere in the app, with or without a
trip -- and one that cannot become a bypass around the trust contract.

## What exists today

Free text already reaches the engine, through `POST /api/v1/trip/event`, which
carries a `message` string and runs `classify_intent` in `llm_service`. It also
requires a `trip_id` and an `EventType`.

That single requirement is the whole problem. Every intelligent path in this
backend is reachable only through a trip, so a search box on a home screen has
nowhere to post, and a question asked while standing in front of a restaurant
before any trip exists cannot be asked at all. SPEC-18's central scenario -- I am
here, is this place worth it -- is exactly that question.

## Why this is not just a text field

An open text box wired to a language model is two things at once: the most
natural interface this product could have, and an unbounded surface for both cost
and ungrounded claims. The two failure modes are worth naming before the design.

The cost one is familiar and this repo already has the machinery for it, built
around the trip path -- semantic cache, circuit breaker, reroute throttle,
asymmetric routing. None of it is reachable from a path that does not exist yet,
so it has to be wired deliberately rather than inherited.

The trust one is more dangerous because it is invisible. SPEC-17 exists so that
no fact reaches a traveller without provenance and a tier. A chat box is the
single easiest place to lose that, because a model will fluently answer "does it
take cash" and the answer will look exactly like a fact we verified. If the box
is allowed to return prose, every guarantee in SPEC-17 is optional in practice.

## Design decisions

1. **One endpoint, and the trip is optional.** A single ask endpoint takes the
   question plus a context object: trip if there is one, coarse location if
   permitted, region, locale, party. Questions asked inside a trip go through the
   same path, so there is one code path to reason about rather than two that
   drift.

2. **The intent set is closed and small.** Place question, plan change, search,
   practical or logistical question, and out of scope. Each maps onto a capability
   that already exists or is already specified -- discovery under SPEC-18, the
   existing trip event path, venue search, corpus knowledge under SPEC-19 -- and
   the router's only job is to choose. An open-ended assistant has no acceptance
   criteria and therefore can never be finished; a closed set can be tested
   exhaustively and extended deliberately.

3. **A plan change with no trip is refused with a reason, not improvised.** The
   honest answer is that there is nothing to change yet, and the useful response
   is an offer to start a trip. Inventing a trip to satisfy the request is how a
   product loses the user's model of what it is doing.

4. **Every answer is a SPEC-17 envelope. There is no prose channel.** The
   response carries values with tier and provenance, and the client renders them
   through the SPEC-22 treatments like any other fact. Where the model knows
   something we cannot source, the tier is `hedge` or `refuse` -- never `assert`.
   This is the decision that keeps the box from quietly becoming a chatbot, and
   it should be enforced by the response type rather than by review.

5. **Guardrails are applied before the model call, not around it.** Cache lookup
   first, then the per-identity budget, then the circuit breaker, and only then
   the model. A budget checked after the spend is an accounting record.

6. **The ask budget is its own budget, and anonymous gets less.** It is not the
   reroute quota; a question is not a replan and sharing a counter would make both
   meaningless. An anonymous identity is free to create in unlimited numbers, so
   it gets the smaller allowance, and signing in raises it. That is also the
   first honest reason we can give a user for making an account, which SPEC-24
   decision 2 asks for.

7. **Classification uses the cheap model; only the discovery path may reach the
   expensive one.** Most questions are answerable from data we hold. Routing
   everything to a large model because the box looks like chat is how the unit
   economics disappear.

8. **Offline, the box stays and answers what it can, immediately.** Where the
   intent resolves against cached data it is answered from cache. Where it does
   not, it says so at once. It does not queue. A question queued now and answered
   three hours later, once the user has walked away and decided, is worse than an
   immediate honest no -- and it teaches people the box is unreliable rather than
   that the network was.

9. **The question itself is a signal, and it is the best one we get.** What
   somebody types unprompted is intent stated in their own words, which no
   tap-through can match. Queries are recorded under the same pseudonymous
   identity as every other signal, and they fall under the SPEC-27 deletion path,
   because free text is the one place a user can put personal information without
   us asking for it.

10. **Classification does not wait on the answer.** The routing decision is fast
    and the client can show what kind of question it thinks was asked while the
    answer resolves. A single opaque wait is the difference between an interface
    that feels alive and one people stop using on a slow connection.

## Tests

- The endpoint answers with no trip in context, and the same question inside a
  trip takes the same path
- Every intent in the closed set has a routing test, and an unroutable question
  returns the out-of-scope refusal rather than a best guess
- A plan-change question with no trip returns the refusal with an offer, asserted
  on the response rather than on a log line
- No response can be constructed without a tier and provenance, proven by a
  negative test rather than by inspection
- A repeated question is served from the semantic cache with no model call,
  asserted on the call count
- The budget is consumed before the model call, proven by a test where the budget
  is exhausted and the model client is asserted never to have been invoked
- An anonymous identity hits its ceiling earlier than a signed-in one
- With the network down, a cache-answerable question answers and a
  non-answerable one refuses immediately without enqueuing
- Each ask emits a signal carrying the query text

## Acceptance

- [ ] Ask endpoint with trip as optional context
- [ ] Closed intent set, each intent routed to an existing capability
- [ ] Response type structurally incapable of carrying an unsourced value
- [ ] Cache, budget and breaker all applied ahead of the model call
- [ ] Separate ask budget, lower for anonymous identities
- [ ] Cheap model classifies; expensive model reachable only via discovery
- [ ] Offline behaviour implemented as answer-or-refuse, never queue
- [ ] Query text recorded as a signal and covered by the deletion path
- [ ] Suite green (R8); verified from `origin/main` (R10)
