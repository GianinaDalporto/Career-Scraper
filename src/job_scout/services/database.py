"""Persistence layer. Adapters never execute SQL."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from job_scout.config.settings import Settings, get_settings
from job_scout.models.enums import FitCategory, WorkMode
from job_scout.models.job import CanonicalJobRecord, JobSourceRef, MobilityFlags, SalarySnapshot, ScoreBreakdown
from job_scout.utils.dates import utcnow

logger = logging.getLogger(__name__)

# Columns added after 0001_init.sql. Live projects may lag migrations; upserts must not send them
# until PostgREST schema cache includes them (PGRST204 otherwise).
JOBS_OPTIONAL_COLUMNS = frozenset(
    {
        "apply_url",
        "direct_employer_url",
        "digest_pending_update",
        "rejected",
        "rejection_reasons",
    }
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


class JobRepository(Protocol):
    def upsert_job(self, job: CanonicalJobRecord, source: JobSourceRef) -> CanonicalJobRecord: ...
    def get_by_fingerprint(self, fingerprint: str) -> CanonicalJobRecord | None: ...
    def list_digest_candidates(self, since: datetime | None, min_score: int) -> list[CanonicalJobRecord]: ...
    def mark_notified(self, fingerprints: list[str], when: datetime) -> None: ...
    def record_scrape_run(self, payload: dict[str, Any]) -> None: ...
    def record_source_health(self, payload: dict[str, Any]) -> None: ...
    def record_digest_run(self, payload: dict[str, Any]) -> None: ...
    def save_fx_rate(self, base: str, quote: str, on: date, rate: Decimal, stale: bool = False) -> None: ...
    def get_fx_rate(self, base: str, quote: str, on: date) -> tuple[Decimal, bool] | None: ...
    def latest_fx_rate(self, base: str, quote: str) -> tuple[Decimal, date, bool] | None: ...
    def list_source_health(self) -> list[dict[str, Any]]: ...
    def last_successful_scrape(self) -> datetime | None: ...
    def last_digest_at(self) -> datetime | None: ...
    def ping(self) -> dict[str, Any]: ...
    def expire_jobs(self, missing_streak: int = 3) -> int: ...
    def recent_scrape_totals(self) -> dict[str, int]: ...


class InMemoryJobRepository:
    """Used by tests. Never talks to production Supabase."""

    def __init__(self) -> None:
        self.jobs: dict[str, CanonicalJobRecord] = {}
        self.sources: dict[str, list[JobSourceRef]] = {}
        self.scrape_runs: list[dict[str, Any]] = []
        self.source_health: dict[str, dict[str, Any]] = {}
        self.digest_runs: list[dict[str, Any]] = []
        self.fx_rates: dict[tuple[str, str, date], tuple[Decimal, bool]] = {}
        self.missing_counts: dict[str, int] = {}

    def upsert_job(self, job: CanonicalJobRecord, source: JobSourceRef) -> CanonicalJobRecord:
        existing = self.jobs.get(job.canonical_fingerprint)
        now = utcnow()
        if existing:
            job.id = existing.id
            job.first_seen_at = existing.first_seen_at
            job.last_notified_at = existing.last_notified_at
            job.source_urls = list(dict.fromkeys([*existing.source_urls, *job.source_urls]))
            job.apply_url = job.apply_url or existing.apply_url
            job.direct_employer_url = job.direct_employer_url or existing.direct_employer_url
        else:
            job.id = job.id or uuid4()
            job.first_seen_at = now
        if source.source_url:
            job.source_urls = list(dict.fromkeys([*job.source_urls, source.source_url]))
        job.apply_url = job.apply_url or source.source_url or source.direct_employer_url
        job.direct_employer_url = job.direct_employer_url or source.direct_employer_url or source.source_url
        if existing and existing.last_notified_at and _material_digest_change(existing, job):
            job.digest_pending_update = True
        elif existing:
            job.digest_pending_update = existing.digest_pending_update
        job.last_seen_at = now
        self.jobs[job.canonical_fingerprint] = job
        self.sources.setdefault(job.canonical_fingerprint, [])
        if not any(s.source_url == source.source_url for s in self.sources[job.canonical_fingerprint]):
            self.sources[job.canonical_fingerprint].append(source)
        self.missing_counts[job.canonical_fingerprint] = 0
        return job

    def get_by_fingerprint(self, fingerprint: str) -> CanonicalJobRecord | None:
        return self.jobs.get(fingerprint)

    def list_digest_candidates(self, since: datetime | None, min_score: int) -> list[CanonicalJobRecord]:
        out = []
        for job in self.jobs.values():
            if not job.active or job.rejected:
                continue
            if job.fit_score is None or job.fit_score < min_score:
                continue
            out.append(job)
        return out

    def mark_notified(self, fingerprints: list[str], when: datetime) -> None:
        for fp in fingerprints:
            job = self.jobs.get(fp)
            if job:
                job.last_notified_at = when
                job.digest_pending_update = False

    def record_scrape_run(self, payload: dict[str, Any]) -> None:
        self.scrape_runs.append(payload)

    def record_source_health(self, payload: dict[str, Any]) -> None:
        self.source_health[payload["source"]] = payload

    def record_digest_run(self, payload: dict[str, Any]) -> None:
        self.digest_runs.append(payload)

    def save_fx_rate(self, base: str, quote: str, on: date, rate: Decimal, stale: bool = False) -> None:
        self.fx_rates[(base.upper(), quote.upper(), on)] = (rate, stale)

    def get_fx_rate(self, base: str, quote: str, on: date) -> tuple[Decimal, bool] | None:
        return self.fx_rates.get((base.upper(), quote.upper(), on))

    def latest_fx_rate(self, base: str, quote: str) -> tuple[Decimal, date, bool] | None:
        matches = [
            (on, rate, stale)
            for (b, q, on), (rate, stale) in self.fx_rates.items()
            if b == base.upper() and q == quote.upper()
        ]
        if not matches:
            return None
        on, rate, stale = max(matches, key=lambda item: item[0])
        return rate, on, stale

    def list_source_health(self) -> list[dict[str, Any]]:
        return list(self.source_health.values())

    def last_successful_scrape(self) -> datetime | None:
        times = [
            row.get("ended_at")
            for row in self.scrape_runs
            if row.get("status") in {"success", "partial"}
        ]
        times = [t for t in times if t]
        return max(times) if times else None

    def last_digest_at(self) -> datetime | None:
        sent = [row.get("generated_at") for row in self.digest_runs if row.get("status") == "sent"]
        sent = [t for t in sent if t]
        return max(sent) if sent else None

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "backend": "memory", "jobs": len(self.jobs)}

    def expire_jobs(self, missing_streak: int = 3) -> int:
        now = utcnow().date()
        expired = 0
        for job in self.jobs.values():
            if job.closing_date and job.closing_date < now:
                job.active = False
                expired += 1
        return expired

    def recent_scrape_totals(self) -> dict[str, int]:
        runs = [row for row in self.scrape_runs if row.get("source") == "all"]
        if not runs:
            return {"jobs_found": 0, "jobs_discarded": 0, "jobs_new": 0}
        row = runs[-1]
        return {
            "jobs_found": int(row.get("jobs_seen") or 0),
            "jobs_discarded": int(row.get("jobs_rejected") or 0),
            "jobs_new": int(row.get("jobs_new") or 0),
        }


class SupabaseFxStore:
    def __init__(self, repo: JobRepository) -> None:
        self.repo = repo

    def get_rate(self, base: str, quote: str, on: date) -> tuple[Decimal, bool] | None:
        return self.repo.get_fx_rate(base, quote, on)

    def latest_rate(self, base: str, quote: str) -> tuple[Decimal, date, bool] | None:
        return self.repo.latest_fx_rate(base, quote)

    def save_rate(self, base: str, quote: str, on: date, rate: Decimal, stale: bool = False) -> None:
        self.repo.save_fx_rate(base, quote, on, rate, stale)


class SupabaseJobRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.has_supabase():
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        from supabase import create_client

        self.client = create_client(self.settings.supabase_url, self.settings.supabase_service_role_key)
        self._jobs_columns: frozenset[str] | None = None
        self._warned_missing_columns = False

    def jobs_columns(self) -> frozenset[str]:
        if self._jobs_columns is None:
            discovered = discover_table_columns(
                self.settings.supabase_url,
                self.settings.supabase_service_role_key,
                "jobs",
            )
            # Never cache an empty discovery — a transient OpenAPI blip would
            # strip apply_url / rejected for the entire process lifetime.
            if not discovered:
                logger.warning("jobs OpenAPI schema empty; will retry on next write")
                return frozenset()
            self._jobs_columns = discovered
            missing = sorted(JOBS_OPTIONAL_COLUMNS - self._jobs_columns)
            if missing and not self._warned_missing_columns:
                self._warned_missing_columns = True
                logger.warning(
                    "jobs table missing columns %s — apply supabase/migrations/0002_job_apply_urls.sql "
                    "and 0003_job_rejection.sql in the Supabase SQL editor. "
                    "Writes will omit those fields until the schema is updated.",
                    missing,
                )
        return self._jobs_columns

    def upsert_job(self, job: CanonicalJobRecord, source: JobSourceRef) -> CanonicalJobRecord:
        now = utcnow()
        existing = self.get_by_fingerprint(job.canonical_fingerprint)
        if existing:
            job.apply_url = job.apply_url or existing.apply_url
            job.direct_employer_url = job.direct_employer_url or existing.direct_employer_url
            job.source_urls = list(dict.fromkeys([*existing.source_urls, *job.source_urls]))
            # Never wipe prior scores when a reject/partial record re-upserts.
            if job.fit_score is None and existing.fit_score is not None:
                job.fit_score = existing.fit_score
                job.fit_category = existing.fit_category or job.fit_category
                job.score_breakdown = existing.score_breakdown or job.score_breakdown
                job.fit_reasons = job.fit_reasons or existing.fit_reasons
                job.concerns = job.concerns or existing.concerns
            if job.rejected and not existing.rejected and existing.fit_score is not None:
                # Prefer keeping the accepted row; caller should usually skip, but belt-and-braces.
                job.rejected = False
                job.rejection_reasons = []
                job.active = existing.active
        job.apply_url = job.apply_url or source.source_url or source.direct_employer_url
        job.direct_employer_url = job.direct_employer_url or source.direct_employer_url or source.source_url
        if source.source_url:
            job.source_urls = list(dict.fromkeys([*job.source_urls, source.source_url]))
        columns = self.jobs_columns()
        payload = _job_row(job, existing, now, columns=columns)
        # Without a rejected column, keep salary/geo rejects out of digests via active=false.
        if job.rejected and "rejected" not in columns:
            payload["active"] = False
        try:
            self.client.table("jobs").upsert(payload, on_conflict="canonical_fingerprint").execute()
        except Exception as exc:  # noqa: BLE001
            missing_col = _pgrst204_column(exc)
            if missing_col and missing_col in payload:
                logger.warning("Dropping unknown jobs column %s after PGRST204 and retrying", missing_col)
                payload.pop(missing_col, None)
                if self._jobs_columns is not None:
                    self._jobs_columns = frozenset(c for c in self._jobs_columns if c != missing_col)
                self.client.table("jobs").upsert(payload, on_conflict="canonical_fingerprint").execute()
            else:
                raise
        stored = self.get_by_fingerprint(job.canonical_fingerprint)
        if stored and stored.id:
            self.client.table("job_sources").upsert(
                {
                    "job_id": str(stored.id),
                    "source_name": source.source_name,
                    "source_job_id": source.source_job_id,
                    "source_url": source.source_url,
                    "direct_employer_url": source.direct_employer_url,
                    "last_seen_at": now.isoformat(),
                },
                on_conflict="source_name,source_job_id",
            ).execute()
            # Re-hydrate URLs onto the returned object for callers / digests.
            stored.apply_url = stored.apply_url or job.apply_url
            stored.direct_employer_url = stored.direct_employer_url or job.direct_employer_url
            stored.source_urls = list(dict.fromkeys([*stored.source_urls, *job.source_urls, source.source_url]))
        return stored or job

    def get_by_fingerprint(self, fingerprint: str) -> CanonicalJobRecord | None:
        result = self.client.table("jobs").select("*").eq("canonical_fingerprint", fingerprint).limit(1).execute()
        rows = result.data or []
        if not rows:
            return None
        return _row_to_job(rows[0])

    def list_digest_candidates(self, since: datetime | None, min_score: int) -> list[CanonicalJobRecord]:
        query = (
            self.client.table("jobs")
            .select("*")
            .eq("active", True)
            .gte("fit_score", min_score)
        )
        if "rejected" in self.jobs_columns():
            query = query.eq("rejected", False)
        result = query.execute()
        jobs = [_row_to_job(row) for row in (result.data or [])]
        if "rejected" not in self.jobs_columns():
            jobs = [job for job in jobs if not job.rejected]
        return self._hydrate_apply_urls(jobs)

    def _hydrate_apply_urls(self, jobs: list[CanonicalJobRecord]) -> list[CanonicalJobRecord]:
        """Attach apply/source URLs from job_sources (and jobs columns when present)."""
        ids = [str(job.id) for job in jobs if job.id]
        if not ids:
            return jobs
        rows: list[dict[str, Any]] = []
        chunk_size = 80
        try:
            for start in range(0, len(ids), chunk_size):
                chunk = ids[start : start + chunk_size]
                result = self.client.table("job_sources").select("*").in_("job_id", chunk).execute()
                rows.extend(result.data or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not hydrate job_sources URLs: %s", exc)
            return jobs
        by_job: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_job.setdefault(str(row.get("job_id")), []).append(row)
        for job in jobs:
            if not job.id:
                continue
            src_rows = by_job.get(str(job.id)) or []
            if not src_rows:
                continue
            urls = [str(r.get("source_url")) for r in src_rows if r.get("source_url")]
            directs = [str(r.get("direct_employer_url")) for r in src_rows if r.get("direct_employer_url")]
            if urls:
                job.source_urls = list(dict.fromkeys([*(job.source_urls or []), *urls]))
            if not job.apply_url:
                job.apply_url = next(
                    (u for u in [*urls, *directs] if u.startswith("http") and "api.smartrecruiters.com" not in u),
                    urls[0] if urls else (directs[0] if directs else None),
                )
            if not job.direct_employer_url:
                job.direct_employer_url = next(
                    (u for u in [*directs, *urls] if u.startswith("http") and "api.smartrecruiters.com" not in u),
                    directs[0] if directs else (urls[0] if urls else None),
                )
        return jobs

    def mark_notified(self, fingerprints: list[str], when: datetime) -> None:
        if not fingerprints:
            return
        payload: dict[str, Any] = {"last_notified_at": when.isoformat()}
        if "digest_pending_update" in self.jobs_columns():
            payload["digest_pending_update"] = False
        self.client.table("jobs").update(payload).in_("canonical_fingerprint", fingerprints).execute()

    def record_scrape_run(self, payload: dict[str, Any]) -> None:
        allowed = {
            "started_at",
            "ended_at",
            "pipeline",
            "source",
            "status",
            "jobs_seen",
            "jobs_new",
            "jobs_updated",
            "jobs_rejected",
            "error_information",
            "duration_seconds",
        }
        row = _json_row({key: value for key, value in payload.items() if key in allowed})
        self.client.table("scrape_runs").insert(row).execute()

    def record_source_health(self, payload: dict[str, Any]) -> None:
        allowed = {
            "source",
            "last_success",
            "last_failure",
            "consecutive_failures",
            "response_status",
            "error_summary",
            "status",
            "jobs_seen",
            "updated_at",
        }
        filtered = {key: value for key, value in payload.items() if key in allowed}
        if "updated_at" not in filtered:
            filtered["updated_at"] = utcnow()
        row = _json_row(filtered)
        self.client.table("source_health").upsert(row, on_conflict="source").execute()

    def record_digest_run(self, payload: dict[str, Any]) -> None:
        self.client.table("digest_runs").insert(_json_row(payload)).execute()

    def save_fx_rate(self, base: str, quote: str, on: date, rate: Decimal, stale: bool = False) -> None:
        self.client.table("fx_rates").upsert(
            {
                "base_currency": base.upper(),
                "quote_currency": quote.upper(),
                "rate_date": on.isoformat(),
                "rate": float(rate),
                "stale": stale,
                "fetched_at": utcnow().isoformat(),
            },
            on_conflict="base_currency,quote_currency,rate_date",
        ).execute()

    def get_fx_rate(self, base: str, quote: str, on: date) -> tuple[Decimal, bool] | None:
        result = (
            self.client.table("fx_rates")
            .select("*")
            .eq("base_currency", base.upper())
            .eq("quote_currency", quote.upper())
            .eq("rate_date", on.isoformat())
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        return Decimal(str(rows[0]["rate"])), bool(rows[0].get("stale"))

    def latest_fx_rate(self, base: str, quote: str) -> tuple[Decimal, date, bool] | None:
        result = (
            self.client.table("fx_rates")
            .select("*")
            .eq("base_currency", base.upper())
            .eq("quote_currency", quote.upper())
            .order("rate_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        return Decimal(str(row["rate"])), date.fromisoformat(row["rate_date"]), bool(row.get("stale"))

    def list_source_health(self) -> list[dict[str, Any]]:
        result = self.client.table("source_health").select("*").execute()
        return result.data or []

    def last_successful_scrape(self) -> datetime | None:
        result = (
            self.client.table("scrape_runs")
            .select("ended_at")
            .in_("status", ["success", "partial"])
            .order("ended_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows or not rows[0].get("ended_at"):
            return None
        return datetime.fromisoformat(rows[0]["ended_at"])

    def last_digest_at(self) -> datetime | None:
        result = (
            self.client.table("digest_runs")
            .select("generated_at")
            .eq("delivery_status", "sent")
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows or not rows[0].get("generated_at"):
            return None
        return datetime.fromisoformat(rows[0]["generated_at"])

    def ping(self) -> dict[str, Any]:
        jobs = self.client.table("jobs").select("id", count="exact").limit(1).execute()
        health = self.client.table("source_health").select("source").limit(1).execute()
        columns = self.jobs_columns()
        missing = sorted(JOBS_OPTIONAL_COLUMNS - columns)
        return {
            "ok": True,
            "backend": "supabase",
            "schema_jobs": True,
            "schema_source_health": health is not None,
            "count": getattr(jobs, "count", None),
            "jobs_columns": sorted(columns),
            "missing_jobs_columns": missing,
        }

    def expire_jobs(self, missing_streak: int = 3) -> int:
        today = utcnow().date().isoformat()
        result = (
            self.client.table("jobs")
            .update({"active": False})
            .lt("closing_date", today)
            .eq("active", True)
            .execute()
        )
        return len(result.data or [])

    def recent_scrape_totals(self) -> dict[str, int]:
        result = (
            self.client.table("scrape_runs")
            .select("jobs_seen,jobs_rejected,jobs_new,source")
            .eq("source", "all")
            .order("ended_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return {"jobs_found": 0, "jobs_discarded": 0, "jobs_new": 0}
        row = rows[0]
        return {
            "jobs_found": int(row.get("jobs_seen") or 0),
            "jobs_discarded": int(row.get("jobs_rejected") or 0),
            "jobs_new": int(row.get("jobs_new") or 0),
        }


def build_repository(settings: Settings | None = None) -> JobRepository:
    settings = settings or get_settings()
    if settings.has_supabase() and not settings.job_scout_dry_run:
        return SupabaseJobRepository(settings)
    logger.info("Using in-memory job repository (no Supabase credentials or dry-run)")
    return InMemoryJobRepository()


def _material_digest_change(existing: CanonicalJobRecord, incoming: CanonicalJobRecord) -> bool:
    if (existing.salary.raw_text or "") != (incoming.salary.raw_text or ""):
        return True
    if existing.closing_date != incoming.closing_date and incoming.closing_date:
        return True
    if (existing.apply_url or "") != (incoming.apply_url or "") and incoming.apply_url:
        return True
    if (existing.direct_employer_url or "") != (incoming.direct_employer_url or "") and incoming.direct_employer_url:
        return True
    if (
        existing.fit_score is not None
        and incoming.fit_score is not None
        and incoming.fit_score - existing.fit_score >= 8
    ):
        return True
    return False


def discover_table_columns(supabase_url: str, service_role_key: str, table: str) -> frozenset[str]:
    """Read PostgREST OpenAPI schema so upserts omit columns not yet migrated."""
    import httpx

    url = f"{supabase_url.rstrip('/')}/rest/v1/"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Accept": "application/openapi+json",
    }
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        spec = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load PostgREST OpenAPI for %s: %s", table, exc)
        return frozenset()

    schemas = (spec.get("components") or {}).get("schemas") or {}
    definitions = spec.get("definitions") or {}
    table_schema = schemas.get(table) or definitions.get(table) or {}
    properties = table_schema.get("properties") or {}
    if properties:
        return frozenset(properties)
    # Fallback: some gateways nest under paths → get → responses
    logger.warning("OpenAPI response had no properties for table %s", table)
    return frozenset()


def filter_job_payload(payload: dict[str, Any], columns: frozenset[str] | None) -> dict[str, Any]:
    """Drop columns absent from the live schema (or omit optional cols when unknown)."""
    if not columns:
        # Unknown schema: omit optional migration columns to avoid PGRST204.
        return {key: value for key, value in payload.items() if key not in JOBS_OPTIONAL_COLUMNS}
    # When discovery succeeded, only send columns PostgREST actually knows.
    return {key: value for key, value in payload.items() if key in columns}


def _pgrst204_column(exc: Exception) -> str | None:
    message = str(exc)
    if "PGRST204" not in message and "schema cache" not in message.lower():
        # supabase-py raises APIError with dict message
        detail = getattr(exc, "message", None) or getattr(exc, "args", [None])[0]
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail)
        else:
            message = str(detail or exc)
    if "schema cache" not in message.lower() and "PGRST204" not in str(exc):
        return None
    import re

    match = re.search(r"Could not find the '([^']+)' column", message)
    return match.group(1) if match else None


def _job_row(
    job: CanonicalJobRecord,
    existing: CanonicalJobRecord | None,
    now: datetime,
    columns: frozenset[str] | None = None,
) -> dict[str, Any]:
    first_seen = (existing.first_seen_at if existing else now)
    pending = bool(job.digest_pending_update)
    if existing and existing.last_notified_at and _material_digest_change(existing, job):
        pending = True
    fit_score = job.fit_score
    fit_category = job.fit_category
    score_breakdown = job.score_breakdown
    fit_reasons = job.fit_reasons
    concerns = job.concerns
    if existing and fit_score is None and existing.fit_score is not None:
        fit_score = existing.fit_score
        fit_category = fit_category or existing.fit_category
        score_breakdown = score_breakdown or existing.score_breakdown
        fit_reasons = fit_reasons or existing.fit_reasons
        concerns = concerns or existing.concerns
    payload = {
        "id": str(existing.id if existing and existing.id else job.id or uuid4()),
        "canonical_fingerprint": job.canonical_fingerprint,
        "title": job.title,
        "company": job.company,
        "company_normalised": job.company_normalised,
        "description": job.description,
        "location_text": job.location_text,
        "city": job.city,
        "region": job.region,
        "country_code": job.country_code,
        "work_mode": job.work_mode.value,
        "remote_scope": job.remote_scope.value,
        "salary_min": _jsonable(job.salary.min_amount),
        "salary_max": _jsonable(job.salary.max_amount),
        "salary_currency": job.salary.currency,
        "salary_period": job.salary.period,
        "salary_min_monthly": _jsonable(job.salary.min_monthly),
        "salary_max_monthly": _jsonable(job.salary.max_monthly),
        "salary_usd_monthly": _jsonable(job.salary.usd_monthly),
        "salary_published": job.salary.published,
        "salary_text": job.salary.raw_text,
        "date_posted": job.date_posted.isoformat() if job.date_posted else None,
        "closing_date": job.closing_date.isoformat() if job.closing_date else None,
        "first_seen_at": first_seen.isoformat() if first_seen else now.isoformat(),
        "last_seen_at": now.isoformat(),
        "active": job.active,
        "rejected": job.rejected,
        "rejection_reasons": job.rejection_reasons or [],
        "fit_score": fit_score,
        "fit_category": fit_category.value if fit_category else None,
        "score_breakdown": score_breakdown.model_dump() if score_breakdown else {},
        "fit_reasons": fit_reasons,
        "concerns": concerns,
        "visa_sponsorship": job.mobility.visa_sponsorship,
        "relocation_assistance": job.mobility.relocation_assistance,
        "work_authorisation_notes": job.mobility.work_authorisation_notes,
        "apply_url": job.apply_url,
        "direct_employer_url": job.direct_employer_url,
        "digest_pending_update": pending,
        "last_notified_at": (
            existing.last_notified_at.isoformat()
            if existing and existing.last_notified_at
            else (job.last_notified_at.isoformat() if job.last_notified_at else None)
        ),
        "updated_at": now.isoformat(),
    }
    return filter_job_payload(payload, columns)


def _json_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in payload.items() if value is not None}


def _row_to_job(row: dict[str, Any]) -> CanonicalJobRecord:
    from uuid import UUID

    from job_scout.models.enums import RemoteScope
    from job_scout.utils.dates import parse_date, parse_datetime

    salary = SalarySnapshot(
        published=bool(row.get("salary_published")),
        raw_text=row.get("salary_text"),
        min_amount=_dec(row.get("salary_min")),
        max_amount=_dec(row.get("salary_max")),
        currency=row.get("salary_currency"),
        period=row.get("salary_period"),
        min_monthly=_dec(row.get("salary_min_monthly")),
        max_monthly=_dec(row.get("salary_max_monthly")),
        usd_monthly=_dec(row.get("salary_usd_monthly")),
    )
    breakdown = None
    if row.get("score_breakdown"):
        try:
            breakdown = ScoreBreakdown.model_validate(row["score_breakdown"])
        except Exception:  # noqa: BLE001
            try:
                raw = dict(row["score_breakdown"])
                allowed = set(ScoreBreakdown.model_fields)
                breakdown = ScoreBreakdown(**{k: v for k, v in raw.items() if k in allowed})
            except Exception:  # noqa: BLE001
                breakdown = None
    return CanonicalJobRecord(
        id=UUID(row["id"]) if row.get("id") else None,
        canonical_fingerprint=row["canonical_fingerprint"],
        title=row.get("title") or "",
        company=row.get("company"),
        company_normalised=row.get("company_normalised"),
        description=row.get("description") or "",
        location_text=row.get("location_text"),
        city=row.get("city"),
        region=row.get("region"),
        country_code=row.get("country_code"),
        work_mode=WorkMode(row.get("work_mode") or "unknown"),
        remote_scope=RemoteScope(row.get("remote_scope") or "unknown"),
        salary=salary,
        mobility=MobilityFlags(
            visa_sponsorship=row.get("visa_sponsorship"),
            relocation_assistance=row.get("relocation_assistance"),
            work_authorisation_notes=row.get("work_authorisation_notes"),
            unknown=row.get("visa_sponsorship") is None,
        ),
        date_posted=parse_datetime(row.get("date_posted")),
        closing_date=parse_date(row.get("closing_date")),
        first_seen_at=parse_datetime(row.get("first_seen_at")),
        last_seen_at=parse_datetime(row.get("last_seen_at")),
        active=bool(row.get("active", True)),
        rejected=bool(row.get("rejected", False)),
        rejection_reasons=list(row.get("rejection_reasons") or []),
        fit_score=row.get("fit_score"),
        fit_category=FitCategory(row["fit_category"]) if row.get("fit_category") else None,
        score_breakdown=breakdown,
        fit_reasons=row.get("fit_reasons") or [],
        concerns=row.get("concerns") or [],
        last_notified_at=parse_datetime(row.get("last_notified_at")),
        apply_url=row.get("apply_url"),
        direct_employer_url=row.get("direct_employer_url"),
        digest_pending_update=bool(row.get("digest_pending_update")),
    )


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
