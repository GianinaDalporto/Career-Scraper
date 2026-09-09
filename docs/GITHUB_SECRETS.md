# GitHub Secrets

Configure these on the GitHub repository (Settings → Secrets and variables → Actions). Never put values in workflow YAML.

Use **Repository secrets** (not Environment secrets).

## Required for scraping + persistence

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Required for the 08:00 digest (Resend)

- `RESEND_API_KEY` — from https://resend.com/api-keys
- `RESEND_FROM` — verified sender, e.g. `Job Scout <jobs@yourdomain.com>`  
  For a quick test only: `Job Scout <onboarding@resend.dev>` (Resend only delivers that to your Resend account email)
- `DIGEST_TO` — your inbox address

SMTP / Gmail app passwords are **not** used anymore.

## Optional official APIs

- `USAJOBS_API_KEY`
- `USAJOBS_USER_AGENT`
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

USAJOBS and Adzuna adapters stay disabled in `config/sources.yaml` until you enable them **and** set the secrets.
