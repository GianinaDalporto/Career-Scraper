-- Job Scout canonical schema
-- Apply in the Supabase SQL editor or via the CLI.
-- Service-role writes from GitHub Actions / local CLI only.
-- Anon clients have no policies and therefore cannot read or write.

create extension if not exists "pgcrypto";

create table if not exists public.jobs (
    id uuid primary key default gen_random_uuid(),
    canonical_fingerprint text not null unique,
    title text not null,
    company text,
    company_normalised text,
    description text,
    location_text text,
    city text,
    region text,
    country_code text,
    work_mode text not null,
    remote_scope text,
    salary_min numeric,
    salary_max numeric,
    salary_currency text,
    salary_period text,
    salary_min_monthly numeric,
    salary_max_monthly numeric,
    salary_usd_monthly numeric,
    salary_published boolean not null default false,
    salary_text text,
    date_posted timestamptz,
    closing_date date,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    active boolean not null default true,
    rejected boolean not null default false,
    rejection_reasons jsonb not null default '[]'::jsonb,
    fit_score integer,
    fit_category text,
    score_breakdown jsonb not null default '{}'::jsonb,
    fit_reasons jsonb not null default '[]'::jsonb,
    concerns jsonb not null default '[]'::jsonb,
    visa_sponsorship boolean,
    relocation_assistance boolean,
    work_authorisation_notes text,
    apply_url text,
    direct_employer_url text,
    digest_pending_update boolean not null default false,
    last_notified_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists jobs_work_mode_score_idx on public.jobs (work_mode, fit_score desc);
create index if not exists jobs_active_idx on public.jobs (active) where active;
create index if not exists jobs_rejected_idx on public.jobs (rejected) where rejected = false;

create table if not exists public.job_sources (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references public.jobs(id) on delete cascade,
    source_name text not null,
    source_job_id text not null,
    source_url text not null,
    direct_employer_url text,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    unique (source_name, source_job_id)
);

create index if not exists job_sources_job_id_idx on public.job_sources (job_id);

create table if not exists public.scrape_runs (
    id uuid primary key default gen_random_uuid(),
    started_at timestamptz,
    ended_at timestamptz,
    pipeline text,
    source text,
    status text,
    jobs_seen integer default 0,
    jobs_new integer default 0,
    jobs_updated integer default 0,
    jobs_rejected integer default 0,
    error_information text,
    duration_seconds numeric,
    created_at timestamptz not null default now()
);

create table if not exists public.source_health (
    source text primary key,
    last_success timestamptz,
    last_failure timestamptz,
    consecutive_failures integer not null default 0,
    response_status integer,
    error_summary text,
    status text,
    jobs_seen integer,
    updated_at timestamptz not null default now()
);

create table if not exists public.digest_runs (
    id uuid primary key default gen_random_uuid(),
    digest_date date not null,
    generated_at timestamptz not null default now(),
    jobs_included integer not null default 0,
    delivery_status text not null,
    recipient text,
    error_information text
);

create table if not exists public.fx_rates (
    id uuid primary key default gen_random_uuid(),
    base_currency text not null,
    quote_currency text not null,
    rate_date date not null,
    rate numeric not null,
    stale boolean not null default false,
    fetched_at timestamptz not null default now(),
    unique (base_currency, quote_currency, rate_date)
);

alter table public.jobs enable row level security;
alter table public.job_sources enable row level security;
alter table public.scrape_runs enable row level security;
alter table public.source_health enable row level security;
alter table public.digest_runs enable row level security;
alter table public.fx_rates enable row level security;

-- No anon policies: the service role bypasses RLS.
-- If you later add a dashboard, grant explicit SELECT policies, never the service role to the browser.
