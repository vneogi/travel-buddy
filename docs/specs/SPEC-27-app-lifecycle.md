# SPEC-27: App Lifecycle, Notifications and Data Rights

> Status: SPECIFIED. Not implemented.
>
> Depends on SPEC-22 for the interruption budget and SPEC-24 for the identity
> model that both notification delivery and deletion have to address.

## Goal

Cover the three consumer obligations that have no owner: reaching the user when
the app is closed, letting them leave with their data or delete it, and keeping a
weeks-stale offline client from corrupting anything.

## Why these are one spec

None of the three is a feature and all three are the kind of work that gets
deferred until a store review or a regulator forces it. They share a shape:
each is cheap while the user base is one person and expensive once it is not, and
each reaches across the client and the server so neither side naturally owns it.

## Notifications

1. **A device token table keyed by identity, not by user.** One person has
   several devices and one device outlives several identities. Tokens carry a
   platform and a revocation timestamp rather than being deleted, because a token
   that stops working is diagnostic information about delivery.

2. **Tokens follow the SPEC-24 merge.** A device registered while anonymous keeps
   working after sign-in. Missing this makes notifications silently stop for
   exactly the users who engaged enough to make an account.

3. **A push is an interruption and goes through the same budget, enforced on the
   server.** SPEC-22 decision 8 gives the budget one owner, and a push that
   bypasses it because the decision was made server-side makes the client budget
   decorative. The server holds the same per-day cap, minimum gap and suppression
   window.

4. **Only trip-critical notifications by default, and the category is declared
   at the call site.** Anything else is opt-in and starts off. A companion app
   that pushes marketing is uninstalled, and the notification permission is spent
   the first time it is abused.

5. **A notification that is not actionable when it arrives is not sent.** The
   interruption is justified by what the user can do about it in that moment.
   This is the same test SPEC-15 applies to checklist prompts, and it belongs here
   too rather than being reinvented per sender.

## Data rights

6. **Export and deletion are endpoints, not a support process.** India's DPDP Act
   covers the primary traveller and GDPR covers the corridor's inbound visitors,
   so this is not optional and the anonymous-first design makes it unusually
   cheap: with no PII collected, most of what we hold is already pseudonymous.

7. **Deletion walks the schema, exactly like the SPEC-24 merge.** The same hole
   applies for the same reason: `signal.user_id` has no foreign key, so nothing
   cascades and nothing complains when a new table is missed. One walk, shared by
   both specs, tested the same way.

8. **Deletion covers the credential aliases.** A merged account has several
   credentials pointing at it under SPEC-24, and deleting the surviving row while
   leaving an alias is the kind of miss that a schema walk catches and a
   hand-written list does not.

9. **Raw signals are deleted; derived aggregates survive, and must not be
   reconstructible to a person.** This is the one genuine tension in the spec and
   it deserves a stated position rather than a quiet default. Behavioural signal
   is the asset, and honouring deletion removes it. The resolution is that the
   derived layer holds population-level facts -- this venue is busy at this hour,
   this transition takes longer than the map says -- which carry no identity and
   are not diminished by one person leaving. Anything in the derived layer that
   could be traced back to an individual is a defect in the derived layer, not a
   reason to weaken deletion.

10. **Export is the same data in a form a human can read.** An export nobody can
    open satisfies the letter of the right and none of its purpose.

## Version and schema safety

11. **The server declares a minimum supported client, and the client refuses to
    write below it -- never to read.** An offline client can hold cached data for
    weeks and its user may be in a place where updating is not possible. Blocking
    reads strands somebody in a foreign country with a phone that has their
    itinerary and will not show it. Blocking writes is enough, because the risk is
    a stale client writing a shape the server no longer understands.

12. **The refusal explains itself and names what still works.** "Update to sync;
    your saved trips are still here" is the difference between a bug report and an
    understood state.

## Tests

- A token registered under an anonymous identity still resolves after that
  identity is merged into an account
- Two subsystems requesting a push inside one window produce one push, asserted
  server-side rather than on the client
- A non-critical category is not delivered without an explicit opt-in
- Deleting an identity leaves zero rows addressed by it or by any of its
  credential aliases, walked from the schema so a new table fails the test
- Deletion leaves derived aggregates intact, and a test asserts no aggregate row
  identifies a single contributor
- Export produces a readable document covering trips, signals and preferences
- A client below the minimum version can read cached data and cannot sync, with
  both halves asserted
- The version refusal names what continues to work

## Acceptance

- [ ] Device token table keyed by identity, with platform and revocation
- [ ] Tokens survive the SPEC-24 merge
- [ ] Server-side interruption budget shared with SPEC-22, with categories
      declared at the call site
- [ ] Trip-critical default; everything else opt-in and off
- [ ] Delete and export endpoints, both walking the schema
- [ ] Aliases covered by deletion
- [ ] Derived aggregates documented as non-identifying, with a test
- [ ] Minimum supported client declared, blocking writes only
- [ ] Suite green (R8); verified from `origin/main` (R10)
