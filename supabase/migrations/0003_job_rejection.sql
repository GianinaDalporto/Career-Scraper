-- Persist hard-filter rejects so digests can exclude them and scrapes stay auditable.
alter table public.jobs
    add column if not exists rejected boolean not null default false,
    add column if not exists rejection_reasons jsonb not null default '[]'::jsonb;

create index if not exists jobs_rejected_idx on public.jobs (rejected) where rejected = false;
