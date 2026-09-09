-- Persist apply links on jobs for digests, and flag material changes after notify.
alter table public.jobs
    add column if not exists apply_url text,
    add column if not exists direct_employer_url text,
    add column if not exists digest_pending_update boolean not null default false;
