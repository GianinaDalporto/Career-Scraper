# Adding a source adapter

Do not add a scraper that bypasses CAPTCHAs, logins, anti-bot walls, or a site's prohibition on automation. Do not add LinkedIn or Indeed.

## 1. Audit first

Add a section to `docs/SOURCE_AUDIT.md` covering: name, URL, region, work-mode coverage, access method, auth, free?, salary, pagination, rate limit, robots, JS required, stability, adapter name, enabled/disabled, reason.

If the source only works via browser automation, document why HTTP/API/RSS cannot work and keep the adapter **disabled** until Playwright is an explicit extra.

## 2. Configuration

Add an entry under `sources:` in `config/sources.yaml`:

```yaml
my_source:
  enabled: false          # enable only after fixture tests pass
  adapter: job_scout.adapters.remote.my_source:MySourceAdapter
  source_type: api        # api | rss | html | ats
  pipelines: [remote]
  regions: [global]
  coverage: {remote: true, hybrid: false, onsite: false}
  preference: specialist_board
  free: true
  auth_required: false
  javascript_required: false
```

For an ATS, add employer slugs to the existing Greenhouse/Lever/Ashby/SmartRecruiters/Workable adapter instead of cloning the parser.

## 3. Code

Create **one module**, for example `src/job_scout/adapters/remote/my_source.py`.

- Subclass `SourceAdapter`.
- Implement `fetch_jobs()` and `parse_job()`.
- Return `RawJobRecord` only.
- Use `job_scout.adapters.http.HttpClient`.
- Do not score, dedupe, send email, or write SQL.
- Catch parse errors per job; let the pipeline record source health.

## 4. Fixtures and tests

Put a static JSON/RSS/HTML snapshot in `tests/fixtures/<source>/`.

Add `tests/unit/test_<source>_adapter.py` that:

- parses the fixture without the network
- asserts `title`, `company`, and application URL are present
- fails if those critical fields disappear (parser-change detection)

## 5. Enable

Set `enabled: true` in `config/sources.yaml` only after tests pass.

Do not edit unrelated adapters to make the new source work.
