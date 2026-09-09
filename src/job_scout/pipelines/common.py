"""Shared pipeline: fetch → parse → normalise → filter → dedupe → score → persist."""

from __future__ import annotations

import logging
import re
import time
from decimal import Decimal
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.config.settings import load_profile, load_salary_policy, load_scoring
from job_scout.models.enums import PipelineName, WorkMode
from job_scout.models.job import CanonicalJobRecord, PipelineStats, RawJobRecord
from job_scout.services.ageing import apply_ageing
from job_scout.services.database import JobRepository
from job_scout.services.deduplication import DuplicateIndex, source_ref_from, to_canonical
from job_scout.services.eligibility import apply_hard_filters
from job_scout.services.fx import FxService
from job_scout.services.normalisation import normalise_job
from job_scout.services.scoring import score_job
from job_scout.services.source_health import record_failure, record_parser_anomaly, record_success
from job_scout.utils.dates import utcnow
from job_scout.utils.text import normalise_key

logger = logging.getLogger(__name__)


def is_family_relevant(title: str, description: str, profile: dict[str, Any]) -> bool:
    """Match family titles/keywords with token-set tolerance for inverted DPSA titles.

    Single-token keywords (water, plant, civil) must hit the title, or the body must
    contain at least two distinct family keywords, to avoid digest junk.
    """
    title_key = normalise_key(title)
    title_tokens = set(title_key.split())
    blob = normalise_key(f"{title} {description or ''}")
    for family in (profile.get("job_families") or {}).values():
        for title_opt in family.get("titles") or []:
            opt = normalise_key(title_opt)
            if not opt:
                continue
            if opt in title_key or opt in blob:
                return True
            opt_tokens = set(opt.split())
            # "Engineer (Mechanical)" ↔ "Mechanical Engineer"
            if opt_tokens and opt_tokens <= title_tokens:
                return True
            # Require substantial overlap — bare "Engineer" must not match "Chief Engineer".
            if len(opt_tokens) >= 2 and title_tokens and title_tokens <= opt_tokens and len(title_tokens) >= 2:
                return True
        keyword_hits = 0
        title_keyword_hit = False
        for keyword in family.get("keywords") or []:
            key = normalise_key(keyword)
            if not key:
                continue
            in_title = False
            in_blob = False
            if len(key) <= 3:
                in_title = bool(re.search(rf"\b{re.escape(key)}\b", title_key))
                in_blob = bool(re.search(rf"\b{re.escape(key)}\b", blob))
            else:
                in_title = key in title_key
                in_blob = key in blob
            if not in_blob and not in_title:
                continue
            # Multi-word keywords are strong enough alone.
            if " " in key and (in_title or in_blob):
                return True
            if in_title:
                title_keyword_hit = True
                keyword_hits += 1
            elif in_blob:
                keyword_hits += 1
        if title_keyword_hit:
            return True
        if keyword_hits >= 2:
            return True
    return False


def attach_usd(job: CanonicalJobRecord, fx: FxService | None) -> None:
    monthly = job.salary.min_monthly or job.salary.max_monthly
    if monthly is None or not job.salary.currency or fx is None:
        return
    try:
        usd, stale = fx.convert(monthly, job.salary.currency, "USD")
        job.salary.usd_monthly = usd
        job.salary.fx_stale = stale
    except Exception as exc:  # noqa: BLE001
        logger.warning("FX convert failed: %s", exc)
        job.flags.append("fx_unavailable")


def _critical_fields(raw: RawJobRecord) -> list[str]:
    missing = []
    if not raw.title:
        missing.append("title")
    if not raw.company:
        missing.append("company")
    if not (raw.apply_url or raw.source_url):
        missing.append("application_url")
    return missing


def run_pipeline(
    *,
    pipeline: PipelineName,
    adapters: Iterable[SourceAdapter],
    repo: JobRepository,
    fx: FxService | None = None,
    expected_work_mode: WorkMode | None = None,
) -> PipelineStats:
    profile = load_profile()
    policy = load_salary_policy()
    scoring = load_scoring()
    stats = PipelineStats(pipeline=pipeline.value)
    index = DuplicateIndex()
    started = utcnow()
    t0 = time.perf_counter()

    for adapter in adapters:
        stats.sources_checked += 1
        source = adapter.source_name
        seen = 0
        parse_errors = 0
        try:
            jobs = list(adapter.fetch_jobs())
        except Exception as exc:  # noqa: BLE001
            stats.sources_failed += 1
            stats.failures.append(f"{source}: {exc}")
            record_failure(repo, source, str(exc), extra={"response_status": None})
            continue

        missing_critical: list[str] = []
        for raw in jobs:
            seen += 1
            stats.raw_jobs += 1
            missing = _critical_fields(raw)
            if missing:
                parse_errors += 1
                missing_critical.extend(missing)
                continue
            try:
                normalised = normalise_job(raw)
            except Exception as exc:  # noqa: BLE001
                parse_errors += 1
                logger.warning("Parse/normalise failed for %s: %s", source, exc)
                continue
            if expected_work_mode and normalised.work_mode not in {expected_work_mode, WorkMode.UNKNOWN}:
                if expected_work_mode == WorkMode.REMOTE and normalised.work_mode != WorkMode.REMOTE:
                    continue
                if expected_work_mode != WorkMode.REMOTE and normalised.work_mode != expected_work_mode:
                    continue
            # Remote pipeline: never coerce UNKNOWN → REMOTE (skips salary/geo gates).
            # Onsite/hybrid: location-driven classification should already resolve office roles;
            # still drop residual UNKNOWN so we don't invent a mode.
            if expected_work_mode and normalised.work_mode == WorkMode.UNKNOWN:
                stats.dropped_work_mode += 1
                continue
            if not is_family_relevant(normalised.title, normalised.description, profile):
                stats.rejected += 1
                continue
            stats.relevant += 1
            decision = apply_hard_filters(normalised, profile=profile, policy=policy, fx=fx)
            normalised.flags.extend(decision.flags)
            canonical = to_canonical(normalised)
            attach_usd(canonical, fx)
            if not decision.accepted:
                canonical.rejected = True
                canonical.rejection_reasons = decision.reasons
                stats.rejected += 1
                if any("salary" in reason for reason in decision.reasons):
                    stats.rejected_salary += 1
                if any("remote_restricted" in reason or "country_not_in_target" in reason for reason in decision.reasons):
                    stats.rejected_geo += 1
                existing = repo.get_by_fingerprint(canonical.canonical_fingerprint)
                # Never let a reject overwrite an accepted, scored row.
                if existing and not existing.rejected and existing.fit_score is not None:
                    continue
                repo.upsert_job(canonical, source_ref_from(normalised))
                continue
            before = repo.get_by_fingerprint(canonical.canonical_fingerprint)
            prior_flags = set(canonical.flags)
            merged = index.add(canonical, source_ref_from(normalised))
            if "duplicate_merged" in merged.flags and "duplicate_merged" not in prior_flags:
                stats.duplicates_merged += 1
            # Score after merge so employer-ATS salary/description upgrades count.
            merged = score_job(merged, profile=profile, scoring=scoring)
            if before and not before.rejected and before.fit_score is not None and merged.rejected:
                merged.rejected = False
                merged.rejection_reasons = []
            stored = repo.upsert_job(merged, source_ref_from(normalised))
            if before is None:
                stats.new += 1
            else:
                stats.updated += 1
            _ = stored

        stats.parse_errors += parse_errors
        if seen == 0:
            employers = adapter.config.get("employers")
            if isinstance(employers, list) and len(employers) == 0:
                record_success(repo, source, 0, extra={"note": "no_employers_configured"})
            else:
                record_failure(repo, source, "zero_jobs_returned")
        else:
            record_success(repo, source, seen, extra={"parse_errors": parse_errors})
            if missing_critical:
                record_parser_anomaly(repo, source, sorted(set(missing_critical)))

    apply_ageing(repo)
    duration = time.perf_counter() - t0
    repo.record_scrape_run(
        {
            "started_at": started,
            "ended_at": utcnow(),
            "pipeline": pipeline.value,
            "source": "all",
            "status": "partial" if stats.sources_failed else "success",
            "jobs_seen": stats.raw_jobs,
            "jobs_new": stats.new,
            "jobs_updated": stats.updated,
            "jobs_rejected": stats.rejected,
            "error_information": "; ".join(stats.failures) or None,
            "duration_seconds": round(duration, 2),
        }
    )
    logger.info(
        "%s: %s sources checked, %s raw, %s relevant, %s new, %s failures",
        pipeline.value,
        stats.sources_checked,
        stats.raw_jobs,
        stats.relevant,
        stats.new,
        stats.sources_failed,
    )
    return stats
