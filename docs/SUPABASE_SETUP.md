# Supabase setup

The GitHub Action and local CLI write with the **service role** key. That key must never appear in client-side code, README examples with real values, or git history.

## Steps

1. Create a free Supabase project.
2. Open **SQL Editor** and run migrations **in order**:
   - `supabase/migrations/0001_init.sql` (full schema for new projects)
   - `supabase/migrations/0002_job_apply_urls.sql` (required if you created the DB from an older 0001)
   - `supabase/migrations/0003_job_rejection.sql` (required if you created the DB from an older 0001)
3. Confirm tables: `jobs`, `job_sources`, `scrape_runs`, `source_health`, `digest_runs`, `fx_rates`.
4. Confirm `jobs` has columns: `apply_url`, `direct_employer_url`, `digest_pending_update`, `rejected`, `rejection_reasons`.
5. Copy **Project URL** and **service_role** key from Project Settings → API.
6. Put them in `.env` locally and in GitHub Actions secrets.
7. Leave Row Level Security enabled. There are no anon policies, so the public anon key cannot read jobs.

`0002` and `0003` are idempotent (`add column if not exists`). Safe to re-run on an existing project that only had the original `0001`.

If those columns are missing, scrapes used to fail with PostgREST `PGRST204`. The Python client now omits missing optional columns and keeps rejects out of digests via `active=false`, but you should still apply `0002`/`0003` so apply links and rejection metadata persist on `jobs`.

The Python repository layer (`job_scout.services.database`) is the only writer. Source adapters never issue SQL.

Tests use `InMemoryJobRepository` and do not touch production.
