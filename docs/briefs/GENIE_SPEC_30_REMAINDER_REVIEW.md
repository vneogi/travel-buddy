# Genie Review Brief -- SPEC-30 Remainder

> REVIEW ONLY. Do not implement, edit, commit, push, or open a PR.
> Review branch: `feat/spec30-remainder`
> Base: `origin/main` at `e689346`
> Product contract: `docs/briefs/GENIE_SPEC_30_REMAINDER.md`

## Goal

Review the completed SPEC-30 remainder before it is proposed for merge. Report
concrete defects, missing acceptance criteria, and test failures. Do not produce
replacement code unless a short snippet is necessary to explain a finding.

## Review scope

Review the full branch diff:

```text
git fetch origin
git diff origin/main...origin/feat/spec30-remainder
```

The implementation should provide:

1. Identity/trip/node-scoped SQLite `node_outcome` persistence with a real
   version 5 to version 6 upgrade.
2. An active-or-elapsed "Did this happen?" control that records visited or a
   closed skip reason.
3. Restore without signal re-emission and double-tap protection.
4. No structural cancel for elapsed or locked nodes.
5. Structural cancel for an active, unlocked skipped node.
6. Outcome-aware `nextMovableStop` targeting.
7. An explicit "Cancel this stop?" dialog naming the selected stop.
8. Keep/dismiss making zero event calls; confirm making exactly one call for
   the node displayed.
9. Existing swap-next behavior unchanged.

## Review priorities

### Correctness

- No `visited_confirmed` or `node_skipped` acknowledgement may appear unless
  the signal was durably inserted into the outbox.
- A failed outbox insert must leave the control retryable.
- Hydration must never emit.
- Local outcomes must key by stable `node_id`, not venue.
- Local outcomes must not rewrite server `TripNode.status`.
- The exact node shown in cancel confirmation must be the node sent.
- Dialog dismissal must not consume reroute quota.

### Lifecycle and offline behavior

- Check Riverpod auto-dispose and every `mounted` boundary across awaits.
- Check process restart, reload, identity isolation, and repeated venues.
- Check database upgrade preserves all version-5 tables and data.
- Check persistence failures remain visible without duplicating signals.

### Tests

Run from `mobile/`:

```text
dart format --output=none --set-exit-if-changed lib test
flutter analyze --no-fatal-infos
flutter test
```

Run from the repository root:

```text
pytest -q -ra
git diff --check
```

The authoring machine did not have Flutter, Dart, or pytest installed. Treat
the commands above as required review gates, not optional confirmation.

Check that widget tests use mocked providers and do not open real network,
SQLite, fonts, or timers. Check that the version-upgrade test uses a real
version-5 SQLite file.

## Required report

Return:

- PASS or CHANGES REQUIRED,
- findings ordered by severity with file and line references,
- exact command results,
- acceptance items not proven,
- any manual Windows/device checks still required.

If no defects are found, say explicitly that the branch is ready for a PR.
Do not modify the branch.
