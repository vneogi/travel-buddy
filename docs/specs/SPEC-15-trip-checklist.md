# SPEC-15: Trip checklist

> Status: SPECIFIED. Not implemented. Post-Laos.
>
> Migration `0017`. Allocation: 0011 venues_rag columns, 0012 booking anchors,
> 0013 preference_choice, 0014 driver_card_shown, 0015 region registry,
> 0016 dietary model, 0017 this.
>
> Related: SPEC-10 supplies the deadlines, SPEC-13 supplies the city, SPEC-02
> supplies the outbox. None of them are hard prerequisites for a plain list.

## Goal

A trip-level and day-level checklist the traveller can add to, where any item
that resolves to a place becomes something the scheduler can slot.

## Why this belongs here and not in the notes app already on the phone

This is the first feature in the product that competes with an incumbent the
user already has open. Reminders and Notes hold a string, sync it, and tick it
off. If the checklist is only a list of strings, it loses, and it should not be
built.

It wins on exactly one thing. "Buy a Barbie doll from Harrods" is not a note --
it is a place, an opening-hours window, and a deadline implied by the flight
home. Knowing the itinerary, the app can say that Harrods is eight minutes from
where the traveller will be at three tomorrow, that it closes at nine, and that
there is a forty-minute gap that fits. No notes app can do that, and no travel
app does it either.

So the rule that justifies the feature: **an item that can be resolved to a
place becomes a candidate node the scheduler can slot; an item that cannot stays
a plain line and is not second-class for it.** Most items will be plain lines,
and that is fine. The resolvable minority is what makes the list worth opening
inside this app.

## The empty-state problem, and what solves it

A checklist that launches empty with a prompt to add items reads as a chore.
Most people will add nothing, the feature will look broken, and its usage
numbers will be read as evidence that nobody wanted it.

The convenience work has a matching gap: the before-trip moments -- visa and
entry, SIM, cash for the cash-only stops, covered shoulders on the temple day,
bags on checkout morning -- had no home in the interface. They are checklist
items. Generating them from the itinerary means the list is useful before the
traveller touches it, and their own items join something that already works
rather than filling a blank box.

Generated items are visually distinct from authored ones and are always
dismissible. A generated item the user deletes is a signal about the generator,
not a failure of the user.

## Design decisions

1. **The raw text never leaves the device.** This is the load-bearing decision.
   Free-text to-dos are the most sensitive data the product would hold: "pick up
   prescription", "buy anniversary gift", "meet Dr Sharma" carry health,
   relationship and religious information in a single line. SPEC-10 refuses
   passenger names and SPEC-11 refuses free text, both to keep the app PII-free.
   A checklist reverses that stance, and it should be reversed deliberately and
   narrowly rather than by accident.

   The raw string is stored in the existing SQLite database and is never sent to
   the server. What syncs is a derived record:

       {
         "item_id": "uuid",
         "category": "shopping",
         "merchant_type": "department_store",
         "place_ref": "venue_id or null",
         "city": "london",
         "scope": "trip | day",
         "status": "open | done | deferred | expired",
         "deferral_count": 3
       }

   Every insight in the signals section below survives this boundary. None of
   them needs the sentence.

2. **Extraction is lazy, optional, and never blocks the user.** Turning free
   text into that structure needs a model call. It happens when connected, after
   the item is already saved, never on keystroke and never as a precondition of
   adding. A failed extraction, an offline device or a disabled model leaves a
   working plain-text item. The feature must be fully usable with extraction
   switched off entirely.

3. **Extraction runs on-device where possible, and sends the minimum where
   not.** If a server call is required, send the item text for the duration of
   the call and do not persist it server-side. Log the derived record, never the
   input. This is the one place the raw string crosses the boundary, so it is the
   one place that needs an explicit retention answer rather than an implied one.

4. **Resolution is offered, never automatic.** When an item resolves to a place
   with a plausible gap, the app offers to slot it. It does not silently rewrite
   the itinerary. An unrequested schedule change is the fastest way to make a
   traveller stop trusting the plan, and the whole product rests on that trust.

5. **One interruption budget, shared with the convenience layer.** Checklist
   reminders and proactive suggestions draw from the same budget rather than
   maintaining separate ones. Two independently reasonable notification policies
   compose into an unreasonable one, and the traveller experiences the sum.

6. **No badge count.** A red number counting unfinished tasks is an anxiety
   generator on a holiday. Surface items by place and time, the way any other
   suggestion surfaces. An unopened checklist should cost the user nothing.

7. **City-scoped items expire quietly.** When the trip leaves the city, an
   unfinished item scoped to it becomes `expired` without a prompt, a summary or
   a guilt screen. It remains visible in the list if the user looks. Expiry is
   data, not a failure to report back.

8. **Day scope and trip scope, nothing deeper.** No projects, no sub-tasks, no
   tags, no assignees. Every one of those is a request that will arrive, and each
   turns a travel utility into a task manager competing on features it will lose.

## Signals

Migration `0017` plus registry entries in the same commit (R5).

| Signal | Why it is worth capturing |
|--------|---------------------------|
| `todo_added` | Category and merchant type segment the traveller: luxury, market, local craft. This is a stated preference, so weight it accordingly. |
| `todo_completed` | Completion rate measures how much a traveller over-plans, which feeds the pacing and fatigue model directly. |
| `todo_deferred` | The most valuable of the four. See below. |
| `todo_expired` | The silent version of deferral, and the honest denominator for the other three. |

**Why deferral is the interesting one.** An item carried forward for five days
and never done is a stated intention the same person's behaviour contradicts.
That is the stated-versus-revealed preference gap, measured within a single
user, with no survey and no forced choice. SPEC-11 spends an entire onboarding
flow buying a weaker version of this, and here it arrives free from a feature
the traveller wanted anyway. Anything derived from `todo_added` alone should be
discounted by the deferral record for the same category.

Inferences from item content stay soft. A doll suggests a child in the party or
a gift recipient; it does not prove one, and it must never be written into
`party_member` as fact. Record it as an inference with a confidence and a source,
or do not record it.

## Tests

- Raw item text is never included in any request body or any log line. Assert
  over the serialized payload, not over intent.
- An item is fully creatable, editable and completable with the network stubbed
  to throw on any call, per R7
- Extraction failure leaves a usable plain-text item, with a test that forces the
  failure
- A resolvable item produces a slot offer and does not mutate the itinerary until
  accepted
- Generated seed items are dismissible, and dismissal emits a signal
- Leaving a city marks its open items `expired` with no user prompt
- `deferral_count` increments across days and survives a restart
- The four signal types are present in the registry and in migration `0017`;
  drift guard green
- Checklist reminders consume the shared interruption budget, proven by a test
  where a spent budget suppresses a checklist reminder

## Acceptance

- [ ] Raw text stored on-device only; a test asserts it appears in no synced
      payload and no log
- [ ] Derived record syncs through the existing SPEC-02 outbox
- [ ] Extraction lazy and optional; feature fully usable with it disabled
- [ ] Server-side retention answer for the extraction call written down, not
      implied
- [ ] Resolvable items offer a slot; nothing is scheduled without acceptance
- [ ] Seeded items generated from the itinerary, visually distinct, dismissible
- [ ] Shared interruption budget with the convenience layer, with a test
- [ ] No badge count anywhere in the UI
- [ ] City-scoped expiry is silent
- [ ] Four signal types in registry plus migration `0017`; drift guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean after Dart writes
