# Genie: SPEC-43 Gap 10 admin IAM -- split (index)

Both parts landed. Do not re-implement. Remainder: log retention.

- Part A: `docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`
  `56ebc00` (PR #148). Fail-closed when the admin token is unset.
- Part B: `docs/briefs/GENIE_SPEC_43_G10_IAM_B.md`
  `17fb0e4` (PR #150). Header compare, 401/200, debug-user is not
  admin.

Do not start Armor, Play Integrity, SQL cache, `derived_feature`,
hosted 0026, Flutter, deploy, or an APK without a new brief.
