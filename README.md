# Nina Career Scraper

USA-first automated job scout for **Nina** (primary teacher, grades 1–5), forked from [Career-Python-Scraper / Job Scout](https://github.com/tiaandelange/Career-Python-Scraper).

Architecture handoff: [`docs/FORK_HANDOFF.md`](docs/FORK_HANDOFF.md)  
Product design: [`DESIGN.md`](DESIGN.md)

## Who it’s for

- **Nina** — South African, B.Ed, TEFL, ~4 years experience, fluent English & Afrikaans
- **Primary teaching** (grades 1–5) in the **United States**, preferring Southern / Bible Belt states (TX, AL, TN, SC, NC, KY, FL, CO, GA, …)
- **Visa sponsorship or self-sponsorship OK** (J-1 / H-1B signals boosted; “must already have US work auth” is **flagged**, not hard-rejected)
- **Remote** full-time or part-time tutoring / online teaching / curriculum / edtech
- **Any US admin assistant** roles

Salary floors (when published): **USD 2 800 / month** or **ZAR 40 000 / month**.

## Quick start

```powershell
cd C:\Users\Tiaan\GitHub\Nina-Career-Scraper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # then fill Supabase + Resend (separate from Job Scout)
python -m job_scout health --memory
python -m job_scout scrape --memory
python -m job_scout digest --memory --print-html
```

## Supabase

Use a **new** Supabase project (do not share Job Scout’s DB).

1. Run `supabase/migrations/0001_init.sql`
2. If upgrading an older schema, also run `supabase/migrations/APPLY_PENDING_JOBS_COLUMNS.sql`
3. Put `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` in `.env` and GitHub Actions secrets

## GitHub Actions

Workflows: scrape (3× daily), digest (08:00 SAST), health.

Secrets: see `docs/GITHUB_SECRETS.md`.

## Commands

```powershell
python -m job_scout scrape
python -m job_scout digest --send
python -m job_scout health
```

## Intended GitHub remote

Public: `https://github.com/GianinaDalporto/Career-Scraper`
