# SPEC-24: Identity Lifecycle

> Status: SPECIFIED. Not implemented.
>
> Depends on SPEC-09 for anonymous device identity, which is the thing that
> creates the problem this spec solves.
>
> The design should be settled before the field test even though the build can
> wait, for the reason in the next section.

## Goal

Let a person sign in without losing what the app already learned about them, and
let one person be one identity across two devices.

## Why the design cannot wait for the build

SPEC-09 is landing now. From the moment it ships, real usage accumulates
`trip_states`, `event_log` and `signal` rows under a device UUID that belongs to
a device rather than to a person. Behavioural signal is the asset this product is
being built around. If sign-in arrives later with no merge path, every row
gathered before that day is stranded under an identity nobody can claim, and the
loss is silent -- the user simply sees an empty app and assumes we lost their
trip.

The cost of deciding this later is not the engineering. It is that the volume of
orphaned data grows every day, and the ambiguity grows with it: after six months
of use there are devices with partial overlaps, shared tablets, and reinstalls,
and the merge rules have to be invented against real messy data instead of
against an empty table.

## What the schema says today

Four facts, all verified against the migrations rather than assumed:

| Table | Identity column | Integrity |
|---|---|---|
| `user_tiers` | `user_id UUID PRIMARY KEY` | the identity root |
| `trip_states` | `user_id UUID NOT NULL` | `REFERENCES user_tiers(user_id)` |
| `event_log` | `user_id UUID NOT NULL` | `REFERENCES user_tiers(user_id)` |
| `signal` | `user_id TEXT` | no foreign key, no type match |

The fourth row is the important one. The table holding the asset is the one table
outside referential integrity, and it does not even share a type with the
identity root. A merge therefore cannot be expressed as a cascade, and neither
can a deletion under SPEC-27. Both have to rewrite `signal` explicitly, and
nothing in the database will complain if a future migration adds a fifth table
and we forget it.

`trip_party` and `party_member` are keyed on `trip_id`, not on a user, so party
data follows the trip and needs no identity rewrite. That is worth stating so
nobody goes looking for work that is not there.

## Design decisions

1. **We do not build authentication.** Supabase Auth owns the provider dance and
   issues the JWT that `security.py` already verifies. Google and Apple only, and
   Apple is not optional once Google is present on iOS. No passwords, because a
   password implies reset mail, rotation, and a support path for an app that has
   no support desk.

2. **Login is optional, and late.** The app stays fully usable signed out;
   SPEC-09 is the normal state and not a stopgap. Sign-in is offered only where
   it buys the user something they can feel -- a second device, a trip shared with
   a companion, or a purchase -- and never as a wall in front of first launch. The
   survey evidence points the same way: cost and food dominated, and nobody
   volunteered an account as a want. An account is our convenience before it is
   theirs, so it has to earn the interruption.

3. **A credential points at an identity; it is not the identity.** An
   `identity_link` table maps a credential -- a device UUID under SPEC-09 or a
   Supabase subject after sign-in -- onto the surviving `user_tiers.user_id`. This
   is deliberately the cheaper of the two available shapes. The pure form
   introduces a `person_id` and demotes `user_tiers.user_id` to one more
   credential, which is more correct and rewrites every identity column in the
   schema to get there. The alias table buys the same ability to recognise a
   returning credential, keeps the audit trail of what was merged into what, and
   costs one table. If a third credential kind ever appears the pure form becomes
   worth it, and the alias table is the migration path to it rather than an
   obstacle.

4. **Merge direction is fixed: anonymous is absorbed into Supabase, never the
   reverse.** This is the same rule already live in `get_or_create_user` as
   upgrade-on-sight for `identity_kind`, extended from a column to the whole row
   set. One rule, stated once, in both places.

5. **Possession of the device secret is the proof.** The client calls the link
   endpoint carrying both the Supabase bearer token and the anonymous device UUID
   from secure storage. Holding the secret is exactly the trust level anonymous
   identity already has, so this adds no new assumption. It does mean an attacker
   who has the device has the data, which was already true.

6. **The merge is one transaction, idempotent under a client-supplied merge id,
   and safe to retry.** The client is frequently on bad hotel wifi; a merge that
   half-applies and cannot be retried is worse than one that never ran.

7. **Union, never dedupe.** If both identities have trips, the merged account has
   all of them. Two devices genuinely planning two trips is an ordinary thing, and
   silently discarding one to make a list look tidy is the kind of loss that ends
   the relationship with the user.

8. **Tier takes the maximum; quota counters also take the maximum.** Never
   downgrade someone who paid. The counter rule is not symmetry for its own sake:
   taking the minimum, or resetting, turns sign-in into a way to refill the daily
   reroute allowance, and any quota with a free reset is not a quota.

9. **Merge is irreversible and recorded.** An `identity_merged` row in
   `event_log` naming both sides. There is no unmerge, because undoing it needs
   per-row provenance of which side each row came from, which we would have to
   carry forever to serve an action nobody has asked for.

10. **Sign-out returns the device to a new anonymous identity and clears the
    local cache.** It does not delete the account, and the new anonymous identity
    is not auto-merged on the next sign-in unless it is the same account. Phones
    get shared and handed around; leaving one person's cached trip on the device
    after sign-out is a privacy failure we would deserve.

11. **Rewriting the identity columns walks the schema; it does not use a
    list.** The set of tables carrying a user identity is discovered at test time
    from the schema, so a table added next year fails the test instead of
    silently keeping orphaned rows. This repo's habit is to make a guard that
    cannot fail into a guard that can (R17), and the `signal` table's missing
    foreign key is precisely the hole such a guard exists to cover.

## Tests

- Merging an anonymous identity holding trips, events and signals into a Supabase
  identity leaves zero rows addressed by the old id, asserted by walking the
  schema for identity columns rather than checking a fixed list
- The same merge applied twice produces the same result as applying it once
- A merge interrupted mid-way leaves the source identity intact and is completable
  on retry
- Both identities holding trips produces the union, with a count assertion that
  fails on dedupe
- A free identity merging into a pro identity stays pro; a pro merging into a free
  stays pro
- Reroute counters after merge equal the maximum of the two, proven by a case
  where the anonymous side had consumed its allowance
- Sign-out clears cached account data and yields a different anonymous id
- Signing in on a second device with its own anonymous history merges that history
  too, so the rule holds on repeat rather than only on first use
- `identity_kind` after merge is `supabase`, and no path can move it back

## Acceptance

- [ ] `identity_link` table with credential kind, credential value, and the
      surviving user id
- [ ] Link endpoint requiring both the bearer token and the device UUID
- [ ] Merge is transactional, idempotent on a merge id, and retry-safe
- [ ] Every identity-carrying table rewritten, including `signal` despite it
      having no foreign key
- [ ] Schema-walking test that fails when a new identity column appears
      unhandled
- [ ] Tier and quota resolution implemented as maximum, with the quota-reset
      exploit covered by a test
- [ ] `identity_merged` recorded in `event_log`
- [ ] Sign-out clears local cache and issues a fresh anonymous identity
- [ ] Google and Apple sign-in wired through Supabase Auth, with no bespoke auth
      code on our server
- [ ] Suite green (R8); verified from `origin/main` (R10)
