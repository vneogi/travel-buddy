# SPEC-25: The Ask Anything Surface

> Status: PARTIAL. Trip-scoped grounded Ask is on main (`30a4270`, from
> `a586e78`). Owner Windows Flutter Ask envelope tests passed. The
> trip-optional surface and full contract below are not.
>
> Depends on SPEC-17 for the response envelope, SPEC-18 for the discovery path,
> and SPEC-22 for how any of it is rendered. It does not depend on SPEC-18 being
> finished: the intent router can return a refusal for the discovery intent and
> still be correct.
>
> SPEC-43 security amendment: the grounded owner-only slice may be completed
> before the security foundation, but production LLM processing of personal
> trip data remains disabled until one redacting allowlist gateway, private
> cache isolation, provider/region/retention approval, and abuse budgets pass.
>
> SPEC-44 architecture amendment: Ask becomes a retrieval-first query service
> after intent classification rather than sharing structural mutation. Bounded
> conversation context, explicit preferences, behavioral features, and catalog
> claims are separate memory planes. No generic traveler-memory blob is created.

## Goal

One way in for a free-text question, from anywhere in the app, with or without a
trip -- and one that cannot become a bypass around the trust contract.

## What exists today

Free text already reaches the engine, through `POST /api/v1/trip/event`, which
carries a `message` string and uses the current deterministic event router. It
also requires a `trip_id` and an `EventType`.

That single requirement is the whole problem. Every intelligent path in this
backend is reachable only through a trip, so a search box on a home screen has
nowhere to post, and a question asked while standing in front of a restaurant
before any trip exists cannot be asked at all. SPEC-18's central scenario -- I am
here, is this place worth it -- is exactly that question.

The trip-scoped composer is not yet a grounded assistant. When no configured
model key is available, or when the model call fails, the server returns a
region-safe canned response. Field evidence recorded in
`docs/AWAITING_VERIFICATION.md` showed that fallback. Even with a key, the
current Ask path does not retrieve catalog hours, dishes, or sourced claims
before generation. Key presence is therefore necessary for a model call but
insufficient for a trustworthy answer.

The current heavy response path can also serialize booking references, notes,
times, and coordinates from itinerary nodes. Grounding does not authorize that
transfer. SPEC-43 defines the outbound DTO and fields that may never cross the
model or embedding boundary.

## Remainder: grounded trip-scoped Ask

Fix the existing trip composer before adding trip-less Ask. This is a bounded
phase on the current `POST /api/v1/trip/event` path; it does not require the
trip-optional endpoint.

### Retrieval precedes generation

Resolve the trip region and current or next relevant node, then retrieve the
available catalog facts for that venue and question. Later sources may include
SPEC-19 claims, but this phase can use the curated venue and dish records that
already exist.

The answer is constructed from retrieved claims. Empty retrieval produces an
immediate hedge or refusal. It never gives the model a blank context and asks it
to improvise a local fact.

Natural-language query is not a second product. Classify the utterance into
a typed command, then retrieve. `ASK_FACT` follows this remainder. Plan
changes become structured trip events (`SWAP_NODE`, `ADD_BOOKING`, or the
existing `EventType` equivalents) and never persist from the Ask response
body. There is no free-form tool loop.

The initial grounded intents are deliberately narrow:

- place identity and location;
- saved opening-hours context, with an explicit staleness/verification hedge;
- known dish and ingredient facts;
- what is current or next on this trip;
- out of scope.

Live opening status, prices, cash acceptance, safety, dietary suitability, and
unrecorded venue details are not inferred from model knowledge.

### Canned fallback is a named state

The response distinguishes:

- grounded deterministic answer;
- grounded model-phrased answer;
- cache hit;
- no configured key;
- retrieval miss;
- budget or breaker refusal;
- model error fallback.

The traveller need not see implementation names, but tests and observability
must distinguish these paths. A generic "check with the venue" message cannot
silently count as a grounded success.

Hosted state records only whether the model key is present and whether a safe
smoke reached the configured provider. It never records the key. A successful
provider call still does not pass acceptance unless the answer is grounded in
retrieved trip data.

### Cost controls

Apply exact public-fact cache, an approved identity/context-scoped private cache,
the separate per-identity Ask budget, and the circuit breaker before any model
call. Anonymous identities receive the lower budget. Record model, token count,
estimated cost, latency, cache status, fallback reason, region, source IDs,
prompt version, and model-policy version without logging the question or any
secret by default. Semantic similarity is not sufficient cache scope for a
private answer.

Use deterministic templates whenever retrieved data already answers the
question. A light model may classify an ambiguous intent or phrase retrieved
facts. The expensive route remains limited to a separately specified discovery
capability.

### Interim trust contract

Until the full SPEC-17 claim registry lands, trip-scoped Ask may return curated
catalog values with source class and a `hedge` or `defer` treatment. It cannot
assert live opening status, price, cash acceptance, or safety. The final
response type still moves toward the SPEC-17 envelope; a free prose string is
not the long-term contract.

### Grounded trip-scoped acceptance

- [ ] Key unset or provider failure returns a named fallback without a 500
- [ ] Retrieval miss returns a hedge/refusal and invokes no generation model
- [ ] A catalog-backed question cites the retrieved venue or dish source
- [ ] Laos trip context cannot produce Dubai venue content
- [ ] Repeated question and context hit cache with zero model calls
- [ ] Exhausted Ask budget invokes no model
- [ ] Cost and fallback telemetry is emitted without question text or secrets
- [ ] Offline mode answers from cache or refuses immediately; it never queues
- [ ] Hosted smoke proves key presence and one grounded answer or honest refusal
- [ ] The deterministic canned fingerprint is not accepted as grounded success

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

9. **The classified intent is a signal; raw question text is not retained by
   default.** What somebody types unprompted can contain booking references,
   health information, another person's data, or any other secret. The closed
   intent and bounded non-text context may be recorded under the appropriate
   SPEC-43 purpose. Raw text remains in the short-lived conversation plane and
   is discarded after response unless a separately specified, explicit,
   revocable research contribution flow is approved. Any retained research text
   follows SPEC-27 export/deletion and is excluded from logs and general caches.

10. **Classification does not wait on the answer.** The routing decision is fast
    and the client can show what kind of question it thinks was asked while the
    answer resolves. A single opaque wait is the difference between an interface
    that feels alive and one people stop using on a slow connection.

11. **NLQ maps to typed commands, not an agent graph.** Classify, retrieve,
    then either a grounded `ASK_FACT` answer or a structured mutation
    proposal on the existing trip-event path. Informational Ask does not
    write itinerary rows. A mutation proposal is shown as a confirmation
    sheet; only traveller confirmation plus the deterministic event path
    persist it. SPEC-44 Phase D owns the split; this spec owns the Ask
    command.

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
- Each ask may emit a purpose-authorized closed intent signal without raw query
  text; declining optional analytics emits neither signal nor outbox row
- Raw question text expires with bounded conversation context and never enters a
  global semantic cache

## Acceptance

- [ ] Ask endpoint with trip as optional context
- [ ] Closed intent set, each intent routed to an existing capability
- [ ] NLQ classifies to a typed command; Ask never persists; mutations use HITL
- [ ] Response type structurally incapable of carrying an unsourced value
- [ ] Cache, budget and breaker all applied ahead of the model call
- [ ] Separate ask budget, lower for anonymous identities
- [ ] Cheap model classifies; expensive model reachable only via discovery
- [ ] Offline behaviour implemented as answer-or-refuse, never queue
- [ ] Purpose-authorized closed intent recorded without raw query text
- [ ] Conversation context is bounded, identity/trip scoped, short-lived, and
      covered by deletion; it cannot become an implicit traveler preference
- [ ] Suite green (R8); verified from `origin/main` (R10)
