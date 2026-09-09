-- Paste into Supabase SQL editor if your project was created from an older 0001_init.
-- Safe to re-run (IF NOT EXISTS).

-- 0002_job_apply_urls
alter table public.jobs
    add column if not exists apply_url text,
    add column if not exists direct_employer_url text,
    add column if not exists digest_pending_update boolean not null default false;

-- 0003_job_rejection
alter table public.jobs
    add column if not exists rejected boolean not null default false,
    add column if not exists rejection_reasons jsonb not null default '[]'::jsonb;

create index if not exists jobs_rejected_idx on public.jobs (rejected) where rejected = false;
