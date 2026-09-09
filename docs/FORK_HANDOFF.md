# Fork handoff — Job Scout (Career-Python-Scraper)

Everything needed to clone this repository and re-target it at a different candidate. The worked example throughout is **Nina — a teacher in the USA, also open to administrative-assistant work**.

Repository root used in all paths below: `C:\Users\Tiaan\GitHub\Career-Python-Scraper`.

Read this alongside the existing docs, which stay authoritative for their own topics:

- `docs/SUPABASE_SETUP.md` — database provisioning
- `docs/GITHUB_SECRETS.md` — secret names
- `docs/ADDING_A_SOURCE.md` — adapter contract
- `docs/SOURCE_AUDIT.md` — per-source legal/technical audit
- `README.md` — day-to-day operation

---

## 1. Project purpose and architecture

Job Scout is an unattended job-discovery pipeline. It runs entirely on GitHub Actions (no desktop required), persists to Supabase, and emails one HTML digest per day. There is no LLM in the scoring path — every score is produced from YAML-configured keyword weights, so results are explainable and free.

The current build is tuned for a South African mechanical / water-infrastructure engineer.

### Layers

Source of truth for the whole flow is `src/job_scout/pipelines/common.py::run_pipeline`.

| Layer | Where | What it does |
| --- | --- | --- |
| Adapters | `src/job_scout/adapters/**` | Fetch and parse one source. Emit `RawJobRecord` only. Never score, dedupe, email, or write SQL. |
| Normalisation | `src/job_scout/services/normalisation.py` | `RawJobRecord` → `NormalisedJobRecord`. Delegates to work-mode, geo, salary and mobility services, and computes the fingerprint. |
| Family relevance | `src/job_scout/pipelines/common.py::is_family_relevant` | Cheap pre-gate against `config/profile.yaml` → `job_families`. Non-matching jobs are counted as `rejected` and dropped without a DB write. |
| Eligibility | `src/job_scout/services/eligibility.py::apply_hard_filters` | Three hard gates: validity, geography, salary. Scoring never sees a job that fails these. |
| Dedupe | `src/job_scout/services/deduplication.py` | In-run `DuplicateIndex` merges the same job across platforms into one canonical record with many source URLs. |
| Score | `src/job_scout/services/scoring.py::score_job` | 0–100 with written `fit_reasons` and `concerns`, driven by `config/scoring.yaml`. Runs **after** merge so an employer-ATS salary upgrade counts. |
| Persist | `src/job_scout/services/database.py` | `SupabaseJobRepository` (production) or `InMemoryJobRepository` (tests / `--memory`). The only component that talks to Supabase. |
| Digest | `src/job_scout/services/email_digest.py` | Selects, renders and (optionally) sends the HTML email via the Resend HTTPS API. |

### Order of operations inside one adapter loop

```
adapter.fetch_jobs()
  → _critical_fields()          # title, company, and one of apply_url/source_url
  → normalise_job()
  → expected_work_mode filter   # pipeline isolation; UNKNOWN is dropped, never coerced
  → is_family_relevant()
  → apply_hard_filters()        # validity → geo → salary
     ├─ rejected → persist as rejected row (unless it would overwrite a scored row)
     └─ accepted → DuplicateIndex.add() → score_job() → repo.upsert_job()
  → source_health record
apply_ageing(repo)              # closing_date in the past → active = false
repo.record_scrape_run(...)
```

### Entry points

`src/job_scout/__main__.py` exposes three subcommands, each delegating to `src/job_scout/orchestration/`:

```powershell
python -m job_scout scrape [--pipeline all|remote|hybrid|onsite] [--memory]
python -m job_scout digest [--send] [--print-html] [--memory]
python -m job_scout health [--memory]
```

Console scripts of the same shape are declared in `pyproject.toml`: `job-scout-scrape`, `job-scout-digest`, `job-scout-health`.

---

## 2. Directory map

```
config/                       Runtime behaviour. No credentials.
  profile.yaml                Candidate identity, job families, geography, hard filters
  scoring.yaml                Weights, keyword lists, penalties, category bands
  salary_policy.yaml          Currency floors, published-salary rules, FX, period conversion
  sources.yaml                Every source, enabled flag, adapter path, pipelines, ATS employer slugs

docs/                         Setup and operational docs (see list above)

src/job_scout/
  __main__.py                 CLI dispatcher
  adapters/
    base.py                   SourceAdapter ABC: fetch_jobs(), parse_job(), health_check()
    registry.py               iter_adapters() — imports adapter classes named in sources.yaml
    http.py                   HttpClient: retries, backoff, rate limiting, host allowlist, URL redaction
    browser.py                Playwright placeholder (not a default dependency)
    mocks.py                  Fixture adapters for tests
    ats/                      greenhouse, lever, ashby, smartrecruiters, workable — one adapter per ATS,
                              employers supplied by config, never cloned per employer
    remote/                   remoteok, remotive, jobicy, himalayas, weworkremotely, remote1stjobs
    regional/                 adzuna, arbeitnow, eures, reliefweb, usajobs, dpsa_circular
  config/settings.py          pydantic-settings `Settings` (env + .env) and YAML loaders
  models/
    enums.py                  WorkMode, FitCategory, SourceType, PipelineName, RemoteScope,
                              JobStatus, RunStatus, DeliveryStatus, SourcePreference
    job.py                    RawJobRecord, NormalisedJobRecord, CanonicalJobRecord, SalarySnapshot,
                              GeoSnapshot, MobilityFlags, ScoreBreakdown, JobSourceRef,
                              FilterDecision, PipelineStats
  orchestration/
    run_scrapers.py           run_all(): pings DB, refreshes FX, runs three pipelines, aggregates stats
    send_digest.py            digest CLI; refuses in-memory fallback when JOB_SCOUT_ENV=github
    health_check.py           Supabase reachability + missing-column check
  pipelines/
    common.py                 run_pipeline() and is_family_relevant() — the shared engine
    remote.py / hybrid.py / onsite.py   Thin wrappers binding a PipelineName + expected WorkMode
  services/
    normalisation.py          Raw → normalised, plus fingerprint()
    work_mode.py              Remote/hybrid/onsite/unknown classification
    geo.py                    Country, city, region, remote-scope extraction
    salary.py                 Salary text parsing, period → monthly, display formatting
    fx.py                     Frankfurter FX with daily cache and stale fallback
    eligibility.py            Hard gates
    deduplication.py          DuplicateIndex, merge_jobs, canonical/raw conversion
    scoring.py                Explainable scoring
    email_digest.py           Selection logic + HTML rendering + Resend send
    database.py               Repository protocol, in-memory and Supabase implementations
    source_health.py          record_success / record_failure / record_parser_anomaly
    ageing.py                 apply_ageing() → repo.expire_jobs()
    mobility.py               Visa, relocation, citizenship, clearance, registration flags
    dpsa_pdf.py               South-African government circular PDF parsing
  utils/                      dates.py, logging.py, text.py (normalise_key, company_key, strip_html, sha256_text)

supabase/migrations/          0001_init.sql, 0002_job_apply_urls.sql, 0003_job_rejection.sql,
                              APPLY_PENDING_JOBS_COLUMNS.sql

tests/
  conftest.py                 Settings isolation, in-memory repo, pre-seeded FX rates, job factories
  unit/                       19 focused test modules
  integration/                test_e2e_fixtures.py, test_live_smoke.py (marker: live)

.github/workflows/            scrape.yml, digest.yml, health.yml
```

---

## 3. Config surfaces

### 3.1 `config/profile.yaml`

Who the candidate is and where they can legally work.

| Key | Purpose |
| --- | --- |
| `candidate.name`, `.summary`, `.qualifications` | Documentation for humans; not read by the scorer. |
| `candidate.do_not_claim` | Documentation of over-claim boundaries; the enforcement lives in `scoring.yaml → digital_overclaim_penalties`. |
| `primary_capabilities`, `digital_transferable`, `business_operational` | Documentation. Not read by code. |
| `job_families` | **Load-bearing.** Read by `is_family_relevant()` (pre-gate) and by `score_job()` (relevance floor). Each family has `titles`, `keywords` and a `weight` 0–1. |
| `geographic.remote` | `flag_unknown`, `reject_if_explicitly_excludes_south_africa`, `keep_unknown`. |
| `geographic.onsite_hybrid_countries` | **Load-bearing.** ISO-2 allowlist used by `in_target_onsite_countries()`. Anything outside it is rejected as `country_not_in_target:XX`. |
| `geographic.assume_work_rights` | Documentation. Work rights are not auto-applied anywhere in code. |
| `hard_filters` | `reject_empty_title`, `reject_expired` are read by `validity_decision()`. The rest document intent. |

Only `job_families`, `geographic.remote`, `geographic.onsite_hybrid_countries` and `hard_filters` change behaviour. Everything else is prose.

### 3.2 `config/scoring.yaml`

| Key | Purpose |
| --- | --- |
| `weights` | Point budget per dimension. They currently total 100. |
| `categories` | Score bands → `FitCategory` (Exceptional / Strong / Good / Possible / Low). |
| `digest_minimum_category` | Lowest category included in the email. Currently `Possible`. |
| `low_score_cutoff` | Passed to `list_digest_candidates()` as the SQL `fit_score >=` bound. Currently 60. |
| `professional_positive`, `skills_positive`, `seniority_positive`, `sectors_high`, `leadership_positive`, `digital_positive`, `operations_positive` | Phrase lists. Each contributes up to its weight, scaled by a hit cap hardcoded in `scoring.py` (3–5 hits). |
| `digital_overclaim_penalties` | +25 penalty and zeroed digital score when matched with no offsetting digital hits; +12 otherwise. |
| `unrelated_roles` | Flat **+40 penalty**. This list currently contains `teacher` and `nurse`. |
| `work_mode_boost`, `mobility_boost`, `mobility_penalty` | Additive/subtractive adjustments. |
| `compensation` | Declared but the actual comp maths is hardcoded in `scoring.py` (see §7). |

### 3.3 `config/salary_policy.yaml`

`currency_floors_monthly` (ZAR/USD/EUR), `public_service.zar_annual_floor` with `source_names`, `default_international_floor`, `rules` (which work modes require a published salary), `fx` provider settings, and `normalisation` divisors used by `to_monthly()`.

All floors are **monthly**. Annual figures are divided by 12; hourly is only converted when the advert states weekly hours.

### 3.4 `config/sources.yaml`

`defaults` (timeouts, retries, `max_pages`, `max_job_age_days`, `max_jobs_per_source`) merge into each source entry. Every source declares:

```yaml
source_key:
  enabled: true
  adapter: job_scout.adapters.remote.my_source:MyAdapter   # import path resolved by registry.py
  source_type: api | rss | html | ats
  pipelines: [remote, hybrid, onsite]                      # which pipelines pick it up
  regions: [...]
  coverage: {remote: bool, hybrid: bool, onsite: bool}
  preference: employer_career | employer_ats | government | specialist_board | aggregator
  employers: [{name: ..., slug: ...}]                      # ATS sources only
```

`preference` matters: `PREFERENCE_RANK` in `deduplication.py` decides which record wins a merge, employer sources beating aggregators.

`disabled_not_implemented` at the bottom documents deliberately excluded sources (LinkedIn, Indeed, PNet, Seek, Glassdoor, Workday, …) with reasons. Keep that section honest in a fork — it is the project's ToS defence.

### 3.5 `.env.example` and environment variables

Copy to `.env` locally. `Settings` in `src/job_scout/config/settings.py` reads these (case-insensitive):

| Variable | Used by |
| --- | --- |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | `SupabaseJobRepository`, `discover_table_columns()` |
| `SUPABASE_ANON_KEY` | Declared, unused by the pipeline |
| `RESEND_API_KEY`, `RESEND_FROM`, `DIGEST_TO` | `send_resend()` |
| `USAJOBS_API_KEY`, `USAJOBS_USER_AGENT` | `UsaJobsAdapter` (returns immediately without a key) |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | `AdzunaAdapter` |
| `JOB_SCOUT_ENV` | `local` or `github`. In `github` mode, health and digest **refuse** to fall back to in-memory. |
| `JOB_SCOUT_LOG_LEVEL`, `JOB_SCOUT_USER_AGENT` | Logging and outbound UA |
| `JOB_SCOUT_DRY_RUN` | Forces the in-memory repository |
| `JOB_SCOUT_SEND_EMAIL` | Equivalent to `digest --send` |
| `JOB_SCOUT_LIVE` | Enables `pytest -m live` |
| `JOB_SCOUT_CONFIG_DIR` | Config directory override; `tests/conftest.py` sets it to the repo `config/` |

### 3.6 GitHub secrets

Repository secrets (Settings → Secrets and variables → Actions), never Environment secrets, never inline in YAML. Names exactly as in `docs/GITHUB_SECRETS.md`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `RESEND_FROM`, `DIGEST_TO`, and optionally `USAJOBS_API_KEY`, `USAJOBS_USER_AGENT`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.

### 3.7 Workflows

| File | Schedule (Africa/Johannesburg) | Notes |
| --- | --- | --- |
| `.github/workflows/scrape.yml` | 10:00, 14:00, 22:00 | 25-min timeout. Verifies secrets, runs `health` as preflight, then `scrape`. |
| `.github/workflows/digest.yml` | 08:00 | 10-min timeout. Sets `JOB_SCOUT_SEND_EMAIL: "true"` and runs `digest --send`. |
| `.github/workflows/health.yml` | 06:30 | 5-min timeout. Keeps the free Supabase project active. |

All three use `actions/checkout@v5`, `actions/setup-python@v6` with Python 3.12 and pip caching, `pip install -e .`, `permissions: contents: read`, and a named `concurrency` group.

The `timezone:` key next to `cron:` is valid GitHub Actions syntax (IANA names, supported since March 2026) and handles DST automatically. Change it, not the cron hour, when forking to another region. Scheduled workflows only fire from the default branch, and GitHub disables schedules on public repos after 60 days of inactivity.

---

## 4. Supabase schema and drift handling

### 4.1 Migrations

Apply in the Supabase SQL editor in order.

| File | Contents |
| --- | --- |
| `supabase/migrations/0001_init.sql` | Full schema. Creates `pgcrypto`; tables `jobs`, `job_sources`, `scrape_runs`, `source_health`, `digest_runs`, `fx_rates`; three `jobs` indexes; enables RLS on all six tables with **no anon policies**. |
| `supabase/migrations/0002_job_apply_urls.sql` | Adds `jobs.apply_url`, `jobs.direct_employer_url`, `jobs.digest_pending_update`. |
| `supabase/migrations/0003_job_rejection.sql` | Adds `jobs.rejected`, `jobs.rejection_reasons`, and the partial index `jobs_rejected_idx`. |
| `supabase/migrations/APPLY_PENDING_JOBS_COLUMNS.sql` | Convenience paste-in that re-applies 0002 + 0003 together. Idempotent. Use this when a project was created from an older `0001_init`. |

The current `0001_init.sql` already contains every column from 0002 and 0003, so a brand-new project only needs `0001`. The later files exist for projects provisioned before those columns were folded in.

Key constraints to preserve in a fork:

- `jobs.canonical_fingerprint` is `not null unique` — it is the upsert conflict target (`on_conflict="canonical_fingerprint"`).
- `job_sources` has `unique (source_name, source_job_id)` and cascades on `jobs` delete.
- `fx_rates` has `unique (base_currency, quote_currency, rate_date)`.
- `source_health.source` is the primary key, so health is upserted per source.
- RLS is on everywhere. The service role bypasses RLS; the anon key can read nothing. Never ship the service-role key to a browser.

### 4.2 How the Python client survives schema drift

Three independent defences in `src/job_scout/services/database.py`:

1. **Column discovery.** `discover_table_columns()` fetches the PostgREST OpenAPI document from `{SUPABASE_URL}/rest/v1/` with `Accept: application/openapi+json` and reads `components.schemas.jobs.properties`. `SupabaseJobRepository.jobs_columns()` memoises the result — but deliberately **does not cache an empty set**, so a transient OpenAPI blip can't strip `apply_url` and `rejected` for the whole process.

2. **Payload filtering.** `filter_job_payload()` intersects the row with the discovered columns. When discovery returned nothing, it falls back to omitting only the post-`0001` optional set:

```20:28:src/job_scout/services/database.py
JOBS_OPTIONAL_COLUMNS = frozenset(
    {
        "apply_url",
        "direct_employer_url",
        "digest_pending_update",
        "rejected",
        "rejection_reasons",
    }
)
```

3. **PGRST204 retry.** If an upsert still fails, `_pgrst204_column()` parses `Could not find the 'X' column ... schema cache` out of the exception, drops that key from the payload, removes it from the cached column set, and retries once.

Degraded-mode behaviour when `rejected` is missing: `upsert_job()` writes `active = False` instead so rejects still stay out of digests, and `list_digest_candidates()` filters rejects in Python rather than SQL.

`python -m job_scout health` surfaces this. `ping()` returns `missing_jobs_columns`; when `JOB_SCOUT_ENV=github` a non-empty list **fails the workflow** with a message pointing at `APPLY_PENDING_JOBS_COLUMNS.sql`. Locally it only warns.

---

## 5. Pipeline rules that matter for a fork

### 5.1 Pipeline isolation and `work_mode`

`classify_work_mode()` in `src/job_scout/services/work_mode.py` returns `REMOTE`, `HYBRID`, `ONSITE` or `UNKNOWN` from title + location + description + the adapter's `work_mode_hint`. Notable behaviour:

- `_FALSE_REMOTE` scrubs phrases where "remote" means geography, not WFH: `remote sensing`, `remote site`, `remote dam`, `fly in fly out`, `fifo`. These are engineering-specific; a teacher fork can trim them but should keep `remote area`/`remote communities` if rural placements are in scope.
- A board-level `remote` hint is **not** trusted when the location names a real city. `hint == REMOTE` plus a location without the word "remote" returns `ONSITE` (if on-site wording is present) or `UNKNOWN` — this is what stops a Denver office post being tagged WFH.
- `_location_implies_onsite()` classifies as on-site when `country_from_text()` resolves the location and it isn't "remote/anywhere/worldwide".
- **`UNKNOWN` is always dropped**, in every pipeline, and counted in `PipelineStats.dropped_work_mode`. See §7.

Each pipeline passes `expected_work_mode`, so remote sources cannot leak into the on-site pipeline.

### 5.2 Geographic gates — `geographic_decision()` in `eligibility.py`

For `REMOTE` jobs the logic is explicitly South-Africa-centric:

- `RemoteScope.US_ONLY` or `AUSTRALIA_ONLY` → rejected as `remote_restricted_to_<scope>`.
- `RemoteScope.EUROPE` → rejected as `remote_restricted_to_europe`.
- `RemoteScope.OTHER_RESTRICTED` → rejected when the restriction set excludes `ZA` (hardcoded `allowed = {"ZA"}`).
- Unknown eligibility is kept and flagged `remote_eligibility_unknown`.

For `ONSITE`/`HYBRID`: `in_target_onsite_countries()` checks `profile.geographic.onsite_hybrid_countries`. Not in the list → `country_not_in_target:XX`.

For `UNKNOWN` work mode the function returns rejected with `work_mode_unknown`, though `run_pipeline` normally drops the job before this point.

`classify_remote_scope()` in `geo.py` walks an ordered chain: worldwide → anywhere → global → EMEA → Africa/South Africa → Europe-only → US-only → Australia-only → other-restricted. `_us_only()` deliberately ignores EEO boilerplate ("eligible to work in the US") and only fires on phrases like "US residents only" or "must be based in the United States".

### 5.3 Salary gates — `salary_decision()`

| Situation | Outcome |
| --- | --- |
| `snapshot.estimated` (Glassdoor-style) | Rejected: `salary_estimate_not_employer_published` |
| On-site or hybrid with no published salary | Rejected: `<mode>_salary_not_published` |
| Remote with no published salary | Accepted, flagged `remote_salary_not_published_allowed` |
| Hourly with no stated weekly hours, on-site/hybrid | Rejected: `hourly_salary_hours_unknown_cannot_verify_floor` |
| Hourly with no stated hours, remote | Accepted, flagged `hourly_without_stated_hours` |
| "Up to X" with no lower bound, on-site/hybrid | Rejected: `salary_up_to_only_no_valid_lower_bound` |
| Published lower bound below the floor | Rejected: `salary_below_floor:<value> <ccy>/month < <floor>` |
| Currency differs from floor currency and FX is unavailable | On-site/hybrid rejected; remote accepted with `fx_unavailable_salary_not_converted` |
| ZAR annual from a source in `public_service.source_names` | Compared against `zar_annual_floor` (annual, not monthly) |

Comparison always uses the **lower** bound (`lower_bound_monthly()` returns `min_monthly` only, never falling back to max). Salary is never invented; `to_monthly()` returns `None` rather than assuming a 40-hour week.

That "on-site and hybrid must publish salary" rule is the single biggest driver of empty on-site results, because most ATS boards omit pay. It is a policy choice in `config/salary_policy.yaml → rules`, not a bug.

### 5.4 Family matching — `is_family_relevant()`

Runs before the hard filters and before any DB write. Rules, in order:

1. A family title matching the job title or the title+description blob → relevant.
2. A family title whose tokens are a subset of the title tokens → relevant. This catches inverted forms like "Engineer (Mechanical)" vs "Mechanical Engineer".
3. The reverse subset, but only when both sides have ≥ 2 tokens, so a bare "Engineer" cannot match "Chief Engineer".
4. Multi-word keywords match on their own.
5. Single-word keywords need either a **title** hit or **two distinct** keyword hits in the body. Keywords ≤ 3 characters use word-boundary regex.

This asymmetry (title hits are strong, body hits are weak) is what keeps generic adverts out of the digest. Keep it in mind when writing keyword lists for a new profile: put the discriminating words where they will appear in titles.

### 5.5 Deduplication

`DuplicateIndex` matches in priority order:

1. `source_name:source_job_id`
2. Canonical URL (query string stripped, fragment **preserved**), skipping shared documents — `_shared_document_url()` treats any `.pdf` and DPSA circular URLs as non-identifying
3. `canonical_fingerprint`
4. Fuzzy match: same `company_key`, same country, same city, same work mode, title `token_set_ratio ≥ 92` **and** description similarity `≥ 86`

The fingerprint itself is `sha256(company_key, title_key, city_key, country, work_mode)` from `normalisation.py::fingerprint`.

`merge_jobs()` picks the base record by `PREFERENCE_RANK` (employer_career < employer_ats < government < specialist_board < aggregator), then upgrades salary (published beats unpublished; more complete beats less), fills missing `direct_employer_url`, `closing_date` and mobility flags, unions `source_urls`, and prefers cleaner plain-text descriptions over entity-encoded HTML.

### 5.6 Rejects

Rejects are persisted, not discarded, so scrapes stay auditable — but never at the cost of a good row. Both `run_pipeline` and `SupabaseJobRepository.upsert_job` guard this. See §7.

### 5.7 Digest selection

`select_digest_jobs()` in `email_digest.py` puts each candidate into one of three buckets:

- **new** — `last_notified_at is None`
- **updated** — `digest_pending_update` is set, or `job_changed_materially()` (salary text changed, closing date appeared, apply/employer URL changed, or score rose by ≥ 8)
- **returning** — everything else; listed compactly in a "STILL OPEN" section

Only `digest --send` calls `mark_notified()`, and only after Resend returns success. A failed send never marks jobs notified.

---

## 6. Adding a source

Full contract is in `docs/ADDING_A_SOURCE.md`. Summary:

1. **Audit first.** Add a row to `docs/SOURCE_AUDIT.md`: name, URL, region, coverage, access method, auth, free, salary availability, pagination, rate limit, robots, JS requirement, stability, adapter name, enabled state, reason. No CAPTCHA bypass, no logins, no anti-bot circumvention, no LinkedIn or Indeed.
2. **Config.** Add an entry to `config/sources.yaml` with `enabled: false`.
3. **Code.** One module under `src/job_scout/adapters/{remote,regional,ats}/`. Subclass `SourceAdapter`, implement `fetch_jobs()` and `parse_job()`, use `job_scout.adapters.http.HttpClient`, return `RawJobRecord` only, and swallow per-job parse errors so one bad row doesn't kill the source.
4. **Fixtures and tests.** A static snapshot in `tests/fixtures/<source>/` plus `tests/unit/test_<source>_adapter.py` asserting title, company and application URL survive parsing. (That fixtures directory does not exist yet — the first person to follow this creates it.)
5. **Enable** only after the tests pass.

**For an existing ATS, do not write an adapter.** Add the board token to the `employers` list:

```yaml
greenhouse:
  employers:
    - {name: Employer Name, slug: their-board-token}
```

The shared adapter iterates `self.config["employers"]`, skips entries with `enabled: false` or no slug, and swallows a 404 per employer. `GreenhouseAdapter` sets `source_name` to `greenhouse:<slug>` so `source_health` tracks each board separately.

Adapter-level search terms are currently **hardcoded in Python**, which is a real friction point for a fork:

| File | Constant |
| --- | --- |
| `src/job_scout/adapters/remote/remotive.py` | `SEARCHES` |
| `src/job_scout/adapters/remote/himalayas.py` | `SEARCHES` |
| `src/job_scout/adapters/remote/weworkremotely.py` | `FEEDS` (category RSS URLs) |
| `src/job_scout/adapters/regional/eures.py` | `KEYWORDS`, `LOCATIONS` |
| `src/job_scout/adapters/regional/adzuna.py` | `QUERIES`, `COUNTRIES`, `_COUNTRY_CURRENCY` |
| `src/job_scout/adapters/regional/usajobs.py` | the keyword tuple inside `fetch_jobs()` |

`remoteok`, `jobicy`, `arbeitnow` and `remote1stjobs` pull an unfiltered feed and rely entirely on `is_family_relevant()` to narrow it.

---

## 7. Known pitfalls from recent fixes

These are the failures the last three commits fixed (`e924e5d`, `2131cd4`, `58d756b`). Preserve the fixes when forking; they are easy to undo by accident.

### 7.1 PGRST204 on `apply_url` and friends

**Symptom:** every upsert fails with `Could not find the 'apply_url' column of 'jobs' in the schema cache`.

**Cause:** the Supabase project was created from an older `0001_init.sql` that predates the 0002/0003 columns.

**Fix in place:** OpenAPI column discovery, payload intersection, and a single PGRST204 retry that drops the offending column (see §4.2).

**What to actually do:** run `supabase/migrations/APPLY_PENDING_JOBS_COLUMNS.sql`. The drift handling is a safety net, not a substitute — without those columns you lose apply links and rejection metadata on `jobs`.

**Trap:** don't "simplify" `jobs_columns()` to cache the discovery result unconditionally. The empty-result guard exists because one failed OpenAPI request would otherwise strip `apply_url` and `rejected` for the entire process lifetime.

### 7.2 UNKNOWN work mode must never be coerced to REMOTE

Previously the remote pipeline treated `UNKNOWN` as remote, which skipped the salary and geography gates entirely — remote roles are allowed to omit salary, so unclassified on-site jobs sailed through unpriced.

```159:161:src/job_scout/pipelines/common.py
            if expected_work_mode and normalised.work_mode == WorkMode.UNKNOWN:
                stats.dropped_work_mode += 1
                continue
```

Losing jobs to `dropped_work_mode` is the intended cost. If a fork sees that counter spike, fix the classifier hints in `work_mode.py` or the adapter's `work_mode_hint` — do not reintroduce the coercion.

### 7.3 Dedupe fingerprint pin

`merge_jobs()` may return the *incoming* record (when an employer ATS outranks an aggregator), and that record carries a different fingerprint. Without pinning, the merged job was persisted under a new key and the original row was orphaned, producing duplicates in the digest.

```79:81:src/job_scout/services/deduplication.py
        merged.canonical_fingerprint = match_id
        if existing.id:
            merged.id = existing.id
```

Related: `canonical_url()` keeps URL fragments, and `_shared_document_url()` excludes PDFs and DPSA circular pages from URL matching — otherwise every post in one weekly circular collapsed into a single job.

### 7.4 Reject must not overwrite an accepted, scored row

The same job can be rejected on one source (no published salary) and accepted on another (employer ATS publishes it). Three guards:

- `run_pipeline` looks up the fingerprint and **skips the write entirely** when an existing row is accepted and scored.
- After scoring, if the previous row was accepted but the merged record is flagged rejected, the rejection is cleared.
- `SupabaseJobRepository.upsert_job` repeats the check as belt-and-braces, and also restores `fit_score`, `fit_category`, `score_breakdown`, `fit_reasons` and `concerns` from the existing row whenever the incoming record has no score.

### 7.5 US "City, ST" geography

`country_from_text()` first tries the longest-match country aliases, then falls back to the last whitespace token: if it is in `US_STATE_ABBRS` the country is `US`; if it is in `AU_STATE_ABBRS` the country is `AU`. That is what makes "Denver, CO" and "Atlanta, GA" resolve to the United States and, in turn, lets `_location_implies_onsite()` classify them as on-site rather than unknown.

Two sharp edges to know about:

- `AU_STATE_ABBRS` contains `sa` and `wa`. `US_STATE_ABBRS` is checked first, so "Seattle, WA" is correctly US — but a location written as "Cape Town, SA" resolves to **Australia**, because no alias matches and `sa` is a valid Australian abbreviation. Write "South Africa" in full.
- `region_from_text()` matches state abbreviations with `\b<abbr>\b` over an alphabetically ordered dict, so short abbreviations like `in`, `or`, `de`, `hi` and `ok` can pick up an unintended state from free text. It only affects the stored `region` field, not filtering.

### 7.6 Secrets only on run steps

Secrets are attached to the steps that need them — the verify step, the health preflight and the scrape/digest step — and never to `actions/checkout`, `setup-python` or `pip install`. That keeps credentials out of the dependency-resolution environment, where a compromised package could read them. Every workflow also declares `permissions: contents: read` and a `concurrency` group. Keep that shape; do not hoist secrets to a job-level `env:` block for convenience.

### 7.7 Other traps worth knowing

- **`scoring.py` duplicates the salary floors.** `floors = {"ZAR": 70000.0, "USD": 4500.0, "EUR": 4000.0}` and the `/ 4500.0` USD fallback are hardcoded at lines 117 and 122, separate from `config/salary_policy.yaml`. Change both or the comp score silently misprices.
- **`scoring.py` has a hardcoded score floor.** A title matching `core_titles` with `sector >= 4` and `penalties < 10` is forced to at least 78, pushing it into Good. Purely mechanical-engineering specific.
- **`fit_reasons` strings are hardcoded English prose** naming "Mechanical/infrastructure language", "acting Chief Engineer / design leadership" and "compatible with working from South Africa". They appear verbatim in the email.
- **`REMOTE_FRIENDLY` in `eligibility.py` (line 17) is dead code** — defined, never referenced. Don't assume changing it does anything.
- **`SupabaseJobRepository.list_digest_candidates` accepts a `since` argument but never uses it** in the query. Digest scope is controlled by `fit_score >=`, `active`, `rejected` and the notified/changed logic, not by time.
- **`digest --send` marks both featured and "returning" jobs notified**, since both appear in the email.

---

## 8. Minimal checklist to fork for a new candidate

### Reuse unchanged

Everything in `src/job_scout/adapters/`, `models/`, `utils/`, `orchestration/`, `pipelines/`, plus `services/` modules `normalisation.py`, `salary.py`, `fx.py`, `deduplication.py`, `database.py`, `source_health.py`, `ageing.py`, `email_digest.py`. The whole `supabase/migrations/` tree and all three workflow files (apart from the timezone). `pyproject.toml` needs no change beyond the project name and description.

### Must change

| # | What | Where |
| --- | --- | --- |
| 1 | New private repo, new Supabase project, run `0001_init.sql`, add the six secrets | GitHub + Supabase |
| 2 | Candidate identity, `job_families` (titles + keywords), `geographic.onsite_hybrid_countries`, `geographic.remote` | `config/profile.yaml` |
| 3 | All phrase lists, `unrelated_roles` (**remove the new occupation from it**), `digital_overclaim_penalties`, weights, bands | `config/scoring.yaml` |
| 4 | `currency_floors_monthly`, `default_international_floor`, `public_service` block (delete if not relevant), `rules` | `config/salary_policy.yaml` |
| 5 | Enable/disable sources, replace ATS `employers` slugs, prune `disabled_not_implemented` reasons | `config/sources.yaml` |
| 6 | Hardcoded floors (line ~117), `/ 4500.0` fallback (line ~122), `core_titles` floor (line ~195), all `reasons.append(...)` prose | `src/job_scout/services/scoring.py` |
| 7 | Remote-scope rejections — the `US_ONLY` / `AUSTRALIA_ONLY` / `EUROPE` rejects and `allowed = {"ZA"}` | `src/job_scout/services/eligibility.py::geographic_decision` |
| 8 | Adapter search constants (`SEARCHES`, `KEYWORDS`, `QUERIES`, `FEEDS`, `COUNTRIES`) | see the table in §6 |
| 9 | Home-country bias: scope chain order, `_extract_country_restrictions`, the DPSA fallback in `geo_from_raw` | `src/job_scout/services/geo.py` |
| 10 | `_FALSE_REMOTE` phrases if the old ones are domain-specific | `src/job_scout/services/work_mode.py` |
| 11 | Delete the SA-government path if unused: `adapters/regional/dpsa_circular.py`, `services/dpsa_pdf.py`, `tests/unit/test_dpsa_pdf.py`, the `dpsa_circular` source entry, and the `public_service` policy block | multiple |
| 12 | `timezone:` on all three cron blocks | `.github/workflows/*.yml` |
| 13 | Fixtures in `tests/conftest.py` (`raw_job`, `canonical_job` default to a Cape Town mechanical engineer) and the profile-specific assertions across `tests/unit/` | `tests/` |
| 14 | Project name, purpose and troubleshooting table | `README.md`, `pyproject.toml` |

### Verification sequence

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
copy .env.example .env      # fill in Supabase + Resend
pytest
python -m job_scout health
python -m job_scout scrape --pipeline remote --memory
python -m job_scout digest --print-html
```

Then run all three workflows once via `workflow_dispatch` before trusting the schedules.

---

## 9. Recommended defaults for a USA teacher / admin-assistant fork (Nina)

### 9.1 Geography

In `config/profile.yaml`:

```yaml
geographic:
  remote:
    origin_anywhere: false
    prefer_scopes: [united_states, us_only, worldwide, anywhere, global]
    keep_unknown: true
    flag_unknown: true
  onsite_hybrid_countries:
    - US
```

In `src/job_scout/services/eligibility.py::geographic_decision`, the remote branch must be inverted. Today `RemoteScope.US_ONLY` is a hard reject; for Nina it is the **preferred** scope, and `EUROPE` / `AUSTRALIA_ONLY` / South-Africa-only restrictions become the rejects. Concretely:

- Accept `US_ONLY`, `WORLDWIDE`, `ANYWHERE`, `GLOBAL`, `UNKNOWN`.
- Reject `EUROPE`, `AUSTRALIA_ONLY`, `AFRICA`, `SOUTH_AFRICA`.
- Change `allowed = {"ZA"}` to `{"US"}` in the `OTHER_RESTRICTED` branch.
- Rename the config key `reject_if_explicitly_excludes_south_africa` to something country-neutral, or keep the key name and just change what it gates — but don't leave the name lying about what it does.

In `src/job_scout/services/geo.py`, reorder `classify_remote_scope()` so the US branch is evaluated before the Africa/EMEA branches, and add `"us residents"` / `"authorized to work in the us"` handling as appropriate. `US_STATES` and `US_STATE_ABBRS` already exist and need no work — the "City, ST" path from §7.5 is exactly what a US fork depends on. Consider deleting `SA_CITIES`, `SA_PROVINCES` and `SA_GENERIC_CENTRES`, or leaving them (harmless, just dead weight).

For a teacher, most roles are on-site and district-bound. Add a state or metro shortlist if Nina isn't willing to relocate — there is no state-level allowlist in the code today, so that would be a small addition to `geographic_decision()` reading a new `profile.geographic.onsite_regions` list against `job.geo.region`.

### 9.2 Sources — keep, drop, add

| Source | Action | Why |
| --- | --- | --- |
| `usajobs` | **Enable — highest priority.** Get a free key at developer.usajobs.gov, set `USAJOBS_API_KEY` and `USAJOBS_USER_AGENT`, and replace the keyword tuple in `fetch_jobs()` with `("Teacher", "Education", "Administrative Assistant", "Program Support Assistant")`. | Official US federal API, publishes salary on nearly every posting, `preference: government`. It already declares `pipelines: [hybrid, onsite]`. Note many federal roles require US citizenship, which `extract_mobility()` detects. |
| `adzuna` | **Enable.** Free developer key, then narrow `COUNTRIES` to `("us",)` and set `QUERIES` to teaching/admin terms. | The only enabled aggregator that reliably carries a salary field for US on-site work, which is what the published-salary rule demands. |
| `greenhouse`, `lever`, `ashby`, `smartrecruiters`, `workable` | **Keep the adapters, replace every employer slug.** Drop the water-engineering boards (mackaysposito, bgeinc, woodardcurran, stanleygroup, AECOM2, Ingerop, Ramboll3). Add charter networks, EdTech companies and staffing firms. Ashby and Workable are already `enabled: false` with empty employer lists — good starting points; Ashby posts salary more often than the others. | Employer ATS boards outrank aggregators in dedupe and give clean apply URLs. |
| `remoteok`, `remotive`, `weworkremotely`, `himalayas`, `remote1stjobs`, `jobicy` | **Keep enabled but retune.** Change the `SEARCHES` constants to `("teacher", "curriculum", "instructional designer", "executive assistant", "administrative assistant", "customer support")`. Swap the `weworkremotely` `FEEDS` from programming/product to customer-support and management categories. | These carry remote tutoring, curriculum and virtual-assistant work. Without retuned queries they return software jobs. |
| `eures` | **Disable.** | EU-only. |
| `arbeitnow` | **Disable.** | European board. |
| `reliefweb` | **Optional.** Keep only if international NGO education work is interesting; it is humanitarian-sector and rarely US-domestic. | |
| `dpsa_circular` | **Delete entirely.** | South African public service. Remove the adapter, `services/dpsa_pdf.py`, its test, the source entry, and the `public_service` block in `salary_policy.yaml`. |
| New: state / district job boards | **Audit before adding.** Many US school districts run Frontline/AppliTrack, PowerSchool or Workday. `disabled_not_implemented` already rules out Workday as an undocumented POST endpoint — apply the same standard. | Follow `docs/ADDING_A_SOURCE.md` and record the verdict in `docs/SOURCE_AUDIT.md`. |

### 9.3 Salary policy

```yaml
currency_floors_monthly:
  USD: 3500          # ≈ $42k/yr — set from Nina's actual walk-away number

default_international_floor:
  currency: USD
  amount_monthly: 3500

rules:
  onsite_requires_published_salary: false   # see note below
  hybrid_requires_published_salary: false
  remote_allows_missing_salary: true
  reject_known_salary_below_floor: true
  range_uses_lower_bound: true
```

Notes that matter more than the numbers:

- **Relaxing `onsite_requires_published_salary` is the key decision.** The engineer fork could afford to reject unpriced on-site roles because ATS boards in that sector are salary-poor and the candidate had a high floor. For a US teacher the opposite is true: district and state postings usually publish a salary schedule, but many private-school and staffing postings do not, and rejecting all of them would gut the pipeline. Start with `false` for both, watch `PipelineStats.rejected_salary`, and tighten later if the digest fills with unpriced noise.
- **Teacher pay is annual and often stated as a schedule range** ("Step 1–10, $52,000–$78,000"). `parse_salary_text()` handles the range and `to_monthly()` divides by 12. It uses the **lower** bound, so a wide schedule range is judged on step 1.
- **Ten-month contracts are not modelled.** A `$52,000` school-year salary is divided by 12, not 10, understating the monthly rate by about 17%. Set the floor with that in mind, or add a period alias if it matters.
- **Hourly matters for admin-assistant roles.** `$22/hour` with no stated weekly hours yields no monthly figure at all: rejected for on-site/hybrid, accepted-with-flag for remote. Relaxing the published-salary rules above sidesteps most of this. If you keep the strict rule, expect `hourly_salary_hours_unknown_cannot_verify_floor` to be a common rejection reason.
- **FX becomes irrelevant.** Everything is USD, so `FxService` will mostly no-op. Leave it — `refresh_usd_basket()` is one cheap request and the failure path is already non-fatal.
- Delete the `public_service` block; it is ZAR/DPSA-specific.

### 9.4 Scoring

Start from a rewritten `config/scoring.yaml`:

- **`unrelated_roles` currently contains `teacher` and `nurse`** — a flat +40 penalty. Removing `teacher` is the single most important edit in the whole fork. Replace the list with genuinely off-profile occupations (software engineer, welder, truck driver, physician).
- **`digital_overclaim_penalties` should be repurposed or emptied.** Its job was stopping an AI-assisted developer from matching senior-CS roles. The equivalent guard for Nina is credential over-claim: penalise postings demanding a specific state licence she doesn't hold, a subject endorsement, an administrator credential, or a master's degree. Rename the concept in the reason strings if you keep the mechanism.
- **`professional_positive`**: classroom teaching, lesson planning, curriculum, differentiated instruction, IEP, classroom management, student assessment, ESL/ELL, special education, K-12, elementary, secondary.
- **`skills_positive`**: state licensure, certification, Praxis, Google Classroom, Canvas, PowerSchool, Microsoft Office, scheduling, calendar management, data entry, records management, parent communication, FERPA.
- **`sectors_high`**: education, K-12, school district, charter school, higher education, EdTech, non-profit, public sector.
- **`operations_positive`**: front office, receptionist, school secretary, office manager, executive assistant.
- **`weights`**: raise `professional_relevance` and `skills`, drop `international_mobility` to near zero (Nina is a US citizen working in the US), and keep `compensation` modest since teacher pay is schedule-bound and won't differentiate candidates.
- Set `digest_minimum_category: Good` and `low_score_cutoff: 70` if the first digests are too noisy, but start at the current `Possible` / `60` to see what the sources actually return.

Then fix `src/job_scout/services/scoring.py` by hand — the YAML alone is not enough:

- Replace the hardcoded `floors` dict and the `/ 4500.0` fallback with the new USD floor.
- Replace `core_titles` with teaching titles, or delete the forced-78 block entirely.
- Rewrite every `reasons.append(...)` and `concerns.append(...)` string. They are shown verbatim in the email, and "Mechanical/infrastructure language matches your background" in a teaching digest destroys trust in the tool immediately.
- Change the remote reason string that says "compatible with working from South Africa".

### 9.5 Schedule and delivery

Update all three workflows to Nina's timezone, for example:

```yaml
on:
  schedule:
    - cron: "0 7 * * *"
      timezone: "America/New_York"
```

Keep the same shape: digest an hour or two before the working day, scrapes spread across the day, health check as the daily keep-alive for the free Supabase project. Set `RESEND_FROM` to a verified domain sender — `onboarding@resend.dev` only delivers to the Resend account owner's own address, which is fine for a smoke test and useless in production.

### 9.6 Expected first-run behaviour

Two things will look broken and are not:

1. **On-site results will be thin at first** until the ATS `employers` list is populated with real district and school-network board tokens. The remote boards fill the gap but skew toward tutoring and EdTech.
2. **`dropped_work_mode` will be non-trivial.** Education postings often name a school without any explicit mode wording. `_location_implies_onsite()` catches most of them via the city/state, but postings with a bare school name and no city fall through to `UNKNOWN` and are dropped. If that count is large, the fix is better location parsing in the adapter, not re-enabling coercion.
