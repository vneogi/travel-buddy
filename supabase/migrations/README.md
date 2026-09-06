# Supabase Migrations

**Rule: ALL schema changes originate in versioned migration files.** The hosted
project has historically applied those files through the SQL editor, so never
run SQL there that has no committed migration counterpart.

## Overview

This directory contains ordered, versioned SQL migrations for the Travel Buddy Supabase database.
Each file is applied once, in order, and is immutable after application.

## Naming convention

```
NNNN_description.sql
```

- `NNNN` — zero-padded sequential number (0001, 0002, …)
- `description` — short snake_case description of what the migration does

Examples:
- `0001_initial_schema.sql` — baseline (existing schema retrofit)
- `0002_signals_core.sql` — signal capture tables

## File structure

Each migration contains:
1. **Forward SQL** — the DDL/DML to apply
2. **Commented ROLLBACK block** at the bottom — the reverse operations to undo the migration
   (Supabase CLI doesn't auto-generate down-migrations; we document them for manual rollback)

```sql
-- Forward
CREATE TABLE foo (...);

-- ROLLBACK:
-- DROP TABLE IF EXISTS foo;
```

## How to create a new migration

1. Decide the next number: `ls supabase/migrations/` and increment
2. Create the file: `supabase/migrations/NNNN_description.sql`
3. Write forward SQL + commented ROLLBACK block
4. Test locally (see below)
5. Commit to git
6. Apply to hosted Supabase (see below)

## How to apply

### To a fresh/local Supabase project (full reset)

```bash
# Apply all migrations in order
supabase db reset
# Or manually:
for f in supabase/migrations/*.sql; do
  psql "$DATABASE_URL" -f "$f"
done
```

### To hosted Supabase (incremental)

```bash
# Apply a specific migration
psql "$SUPABASE_DB_URL" -f supabase/migrations/0002_signals_core.sql
```

Or via the Supabase CLI:
```bash
supabase db push
```

### Verify current state

This project does not have a trustworthy CLI migration-history table. Do not
infer hosted state from `supabase migration list`. Run the live sentinel query
in `docs/HOSTED_STATE.md`; that document is the only current hosted ledger.

## Rules

1. **Never edit an applied migration.** If you need to change something, create a NEW migration
   that alters/drops/recreates. The history is append-only.
2. **Always include a ROLLBACK block** (commented out). Even if you never run it, it documents
   the reverse and proves you thought about it.
3. **Use IF NOT EXISTS / IF EXISTS** for idempotency where possible (especially in the baseline
   migration which may be applied to an already-populated DB).
4. **Test on a fresh project** before applying to production — `0001` through `000N` should
   produce the complete schema from scratch.
5. **One logical change per migration.** Don't bundle unrelated schema changes.
6. **Commit the migration before applying to production.** Git is the source of truth.

## Current migrations

The repository contains ordered migrations `0001_initial_schema.sql` through
`0024_session_start.sql`. All are verified on the hosted project as recorded in
`docs/HOSTED_STATE.md`. The directory listing, not a duplicated table here, is
the source of truth for filenames and descriptions.

## Connection strings

- **Local**: `postgresql://postgres:postgres@localhost:54322/postgres`
- **Hosted**: Use `SUPABASE_DB_URL` from your `.env` (format: `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`)
