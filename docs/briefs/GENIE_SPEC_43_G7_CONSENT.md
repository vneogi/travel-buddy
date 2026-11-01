# Genie brief: SPEC-43 Gap 7 -- fail-closed optional ingest

Landed on `main` as `e3eaa81` (PR #112). Do not re-implement this slice.
Next: Gap 8 identity-scoped semantic cache
(`docs/briefs/GENIE_SPEC_43_G8_CACHE.md`). Do not start Gap 8,
Gap 10, Gap 11, remaining Gap 9 GPS/`derived_feature`, hosted 0026,
Flutter consent UI, deploy, or an APK without a new brief.

## What shipped

Optional personalization and analytics types reject per item with
`consent_required` until a grant ledger exists. Necessary
trip-operation types still ingest. `arrival_delta` derive is gated
on analytics; `observed_duration` is not. Suite tests grant via
autouse unless marked `real_consent`.

Remainders: Flutter outbox still enqueues loves (server rejects);
no ledger/UI/withdrawal; `party_context.age_bands` still stamped;
`dish_ordered` is mapped but not in the personalization sweep test.
