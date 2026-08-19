# Ways of Working

Written Aug 15 2026, at the point where this project handed over between
planning sessions for the first time. `ENGINEERING_RULES.md` records what the
code must do. This file records how the people and agents around the code
behave, which turned out to matter just as much: nearly every defect worth
recording in this repo survived review because of a process gap rather than a
technical one.

Read this alongside `PROJECT_STATUS.md`. That file says where the project is.
This one says how to move it without breaking the things that took months to
learn.

## 1. Who does what

Three parties, with different evidence available to each. Most process failures
here trace back to one party claiming something only another party could know.

**The planning agent** owns product design, specification, sequencing, review
and documentation. It writes docs and specs directly to the repository. It has
no Python environment: no pytest, no ruff, no database. It must never state
that a test passes. When the planning agent changes, the baton is
`docs/HANDOFF_PLANNING_AGENT.md`; the contracts stay this file and
`docs/ENGINEERING_RULES.md`.

**The execution agent** (Genie Code, on Databricks) owns application code,
migrations and the test suite. It has a real environment and is the only party
that can produce a test result. Code changes go through a pull request.
Documentation-only changes may go direct to `main`.

**The project owner** owns the laptop, and therefore everything requiring a
device, a real Flutter build, PowerShell, or live database credentials. A large
class of claims in this project can only ever be settled here, which is why
`AWAITING_VERIFICATION.md` exists as a standing list rather than a temporary
one.

The division is not bureaucracy. It exists because each party can produce
evidence the others cannot, and the failure mode is quiet: an agent that
restates another's result as its own finding launders an unverified claim into
an apparently verified one.

## 2. The evidence rule

This is the single most important practice in the project, and everything in
section 4 is a special case of it.

**Say what you saw. Mark everything else unverified, in the same breath.**

A good example, from a review of the R5 relocation PR: "I did not re-run pytest
here. The execution agent's result is unverified on this machine." That sentence
costs nothing and it keeps the provenance of every claim visible. Its absence is
how a repository ends up believing things nobody checked.

Concrete forms this takes:

- Never report a test result you did not watch run.
- After writing a document, read it back from `origin`, not from your working
  copy. A commit once rebuilt `PROJECT_STATUS.md` only partially and left the
  file asserting two contradictory things about signal types, silently.
- After a merge, read the merged tree before declaring the work done.
- When an agent reports what it did, review the diff rather than the report.
  The report is a claim about the diff; only the diff is evidence.
- A green suite is not evidence that a particular guard works. See section 5.

## 3. Where information goes

Chat is not storage. Any conversation may end without warning, so the practice
is to write things down as they are decided rather than at the end of a session.
The routing is fixed:

| Kind of thing | Where it goes |
|---|---|
| A product or design decision | a spec under `docs/specs/` |
| A finding, gap or risk | the risk table in `PROJECT_STATUS.md` |
| A lesson learned from a defect | a numbered rule in `ENGINEERING_RULES.md` |
| A dated observation, or something only a device can settle | `AWAITING_VERIFICATION.md` |
| An instruction for the execution agent | a brief under `docs/briefs/` |

Two rules keep the set coherent. Exactly one document owns any given list; when
two documents held the device-day task order, they drifted and began
contradicting each other within days. And dated observations belong only in
`AWAITING_VERIFICATION.md`, so the other documents can be read as current
without checking when each sentence was written.

## 4. Reviewing the execution agent

Assume competence and verify anyway. The execution agent is good, and the
defects that reached `main` were mostly subtle enough that a careless review
would have passed them.

Read the diff, not the summary. Then look for the specific things that have gone
wrong here before:

- **A new column, table or field with no writer.** Ask who writes it and who
  reads it. `venue_external_id` was created, tested, and had no writer at all;
  `observed_duration_minutes` was hardcoded to null by the only code that could
  have populated it. Both passed review.
- **A computed value that is discarded.** Signal provenance was calculated on
  every request and thrown away, so clock skew was never once persisted. The
  only symptom was analytics that could not exist.
- **A guard that cannot fail.** Section 5.
- **A vocabulary declared in more than one place.** Price bands were defined
  independently in several migrations and drifted. The fix is a guard that
  parses both sides and compares them as sets, not a comment asking people to
  keep them aligned.
- **Dead code left behind by a fix**, including assignments to values nothing
  reads.

Separate blocking from non-blocking explicitly, and say which is which. A review
that mixes "this is wrong" with "this could be tidier" makes the author guess,
and they will guess wrong under time pressure.

## 5. Proving a guard actually guards

R17 in `ENGINEERING_RULES.md` has seven recorded instances of a test that could
not fail. It is the most persistent defect class in the project, so the process
around it is worth stating separately from the rule.

Before trusting a new test, break the thing it guards and watch it fail. Then
check three things that the naive version of that ritual misses:

1. **Which test failed, by name.** A red suite is not the proof. Five passing
   structural tests in one file once hid a single inert test, because the
   sabotage turned the file red for an unrelated reason.
2. **Whether the test reaches the code the way production does.** A test that
   builds the input itself and hands it to the storage layer proves the storage
   layer works. It says nothing about the router that was dropping the value.
   Go in through the real entry point.
3. **Whether the test double can express the failure.** If a fake cannot
   represent the broken behaviour, no assertion above it can catch the broken
   behaviour. When sabotage unexpectedly still passes, suspect the double before
   the assertion.

The oldest instance is worth remembering as a shape: the venue loader's own test
module passed continuously throughout the period the loader could not load the
committed data. Tests passing and the system working are different claims.

## 6. Writing a brief for the execution agent

A brief is run by an agent with no access to the conversation that produced it.
Write it so it can be executed start to finish without improvising.

- State the goal, then the exact steps, then how to prove it worked.
- Name the sabotage proof: which line to break, and which named test must fail.
- Include hard stops where a wrong result must halt the work rather than flow
  into the next step. The device-day brief refuses to continue if the Dubai
  export returns fewer rows than expected, because everything after that step
  can destroy the thing the step was protecting.
- Never ask it to edit the brief itself.
- State the ASCII constraint (R14) where it applies.
- Prefer verification the agent can perform over verification it must claim.

## 7. Writing documentation safely

- Pure ASCII outside the allowlist in `tests/test_docs_hygiene.py`, and the
  allowlist may only shrink.
- Do not reference a spec number before the spec file exists. The hygiene guard
  treats an unresolvable `SPEC-NN` as a finding, because it usually means an
  uncommitted spec.
- Avoid embedding counts that will drift. A number written into prose becomes
  wrong silently and stays quoted for months.
- Prefer stating what was verified and how over stating that something is
  complete.
- When rewriting a document that has gone stale, say explicitly in the commit
  message which claims were wrong and are now removed. A reader holding an old
  copy needs to be able to tell.

## 8. Scope discipline

The most valuable moves in this project removed work rather than adding it.

The dietary suitability claim was retired outright, as a decision record, once
it became clear no available source could support it; ingredient facts stayed,
informational and disclaimed. The offline vault shrank to a thin hotel-rescue
entry once it turned out the offline cache and the driver card already covered
what the field test needed. Both were found by asking what a feature actually
delivers beyond what already exists, before agreeing to build it.

So: before accepting a spec into the near-term plan, check what already-shipped
work overlaps it. And prefer descoping a promise the data cannot support over
building a mechanism to fake it.

## 9. Working with the project owner

Be direct. Disagree in plain terms when the evidence supports it, including
about lists the owner previously approved: two documents in this repository
contradicted each other about what the October field test needs, and that was
found by a review willing to say the written plan was incomplete.

Lead with the conclusion, then the reasoning. Offer discrete choices rather than
open questions when a decision is needed. Do not ask for a decision that the
documents already answer.

And keep one thing in view: the forcing function is a real trip, on a real date,
with a real traveller. A guard that cannot fail, a column with no writer, and a
document that contradicts itself are all the same problem in different clothes,
which is that something looked done and was not. On October 2 the difference
will not be recoverable.
