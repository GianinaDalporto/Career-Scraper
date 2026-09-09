"""Run Remote, Hybrid and On-site pipelines. One adapter failure is not fatal."""

from __future__ import annotations

import argparse
import json
import logging
import time

from job_scout.config.settings import get_settings
from job_scout.pipelines.hybrid import run_hybrid_pipeline
from job_scout.pipelines.onsite import run_onsite_pipeline
from job_scout.pipelines.remote import run_remote_pipeline
from job_scout.services.database import InMemoryJobRepository, SupabaseFxStore, build_repository
from job_scout.services.fx import FxService, InMemoryFxStore
from job_scout.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def run_all(memory: bool = False) -> dict:
    settings = get_settings()
    configure_logging(settings.job_scout_log_level)
    if not memory and not settings.job_scout_dry_run and not settings.has_supabase():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are missing. "
            "Add them as GitHub repository secrets (or use --memory)."
        )
    repo = InMemoryJobRepository() if memory or settings.job_scout_dry_run else build_repository(settings)
    try:
        ping = repo.ping()
        logger.info("Database ping: %s", ping)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Supabase unreachable or schema missing: {exc}") from exc

    fx_store = InMemoryFxStore()
    if hasattr(repo, "save_fx_rate") and not memory:
        fx_store = SupabaseFxStore(repo) if settings.has_supabase() and not memory else InMemoryFxStore()
    fx = FxService(store=fx_store, settings=settings)
    try:
        fx.refresh_usd_basket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FX refresh failed; conversions will use cache if present: %s", exc)

    t0 = time.perf_counter()
    pipeline_errors: list[str] = []

    def _safe(name: str, fn):
        try:
            return fn(repo, fx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s pipeline failed", name)
            pipeline_errors.append(f"{name}: {exc}")
            from job_scout.models.job import PipelineStats

            return PipelineStats(pipeline=name, failures=[str(exc)])

    remote = _safe("remote", run_remote_pipeline)
    hybrid = _safe("hybrid", run_hybrid_pipeline)
    onsite = _safe("onsite", run_onsite_pipeline)
    runtime = round(time.perf_counter() - t0, 2)
    summary = {
        "remote": remote.model_dump(),
        "hybrid": hybrid.model_dump(),
        "onsite": onsite.model_dump(),
        "runtime_seconds": runtime,
        "accepted": remote.new + hybrid.new + onsite.new,
        "duplicates_merged": remote.duplicates_merged + hybrid.duplicates_merged + onsite.duplicates_merged,
        "rejected_salary": remote.rejected_salary + hybrid.rejected_salary + onsite.rejected_salary,
        "pipeline_errors": pipeline_errors,
    }
    logger.info("Scrape summary: %s", json.dumps(summary, default=str))
    if pipeline_errors:
        raise RuntimeError("; ".join(pipeline_errors))
    total_checked = remote.sources_checked + hybrid.sources_checked + onsite.sources_checked
    total_failed = remote.sources_failed + hybrid.sources_failed + onsite.sources_failed
    total_raw = remote.raw_jobs + hybrid.raw_jobs + onsite.raw_jobs
    if total_checked > 0 and total_failed >= total_checked:
        raise RuntimeError(
            f"All {total_checked} sources failed across pipelines; scrape produced no usable data."
        )
    if total_checked > 0 and total_raw == 0 and total_failed > 0 and total_failed == total_checked:
        raise RuntimeError("Scrape completed with zero raw jobs and every source failed.")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Job Scout pipelines")
    parser.add_argument("--pipeline", choices=["all", "remote", "hybrid", "onsite"], default="all")
    parser.add_argument("--memory", action="store_true", help="Do not write to Supabase")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.job_scout_log_level)
    try:
        if args.pipeline == "all":
            run_all(memory=args.memory)
            return 0
        repo = InMemoryJobRepository() if args.memory else build_repository(settings)
        fx = FxService(settings=settings)
        if args.pipeline == "remote":
            print(run_remote_pipeline(repo, fx).model_dump())
        elif args.pipeline == "hybrid":
            print(run_hybrid_pipeline(repo, fx).model_dump())
        else:
            print(run_onsite_pipeline(repo, fx).model_dump())
        return 0
    except Exception:
        logger.exception("Scrape failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
