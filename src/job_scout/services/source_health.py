"""Per-source health. One failure must not stop other adapters."""

from __future__ import annotations

import logging
from typing import Any

from job_scout.services.database import JobRepository
from job_scout.utils.dates import utcnow

logger = logging.getLogger(__name__)


def record_success(repo: JobRepository, source: str, jobs_seen: int, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "source": source,
        "last_success": utcnow(),
        "consecutive_failures": 0,
        "status": "success",
        "jobs_seen": jobs_seen,
        "error_summary": None,
        **(extra or {}),
    }
    repo.record_source_health(payload)


def record_failure(repo: JobRepository, source: str, error: str, extra: dict[str, Any] | None = None) -> None:
    existing = next((row for row in repo.list_source_health() if row.get("source") == source), {})
    consecutive = int(existing.get("consecutive_failures") or 0) + 1
    payload = {
        "source": source,
        "last_failure": utcnow(),
        "consecutive_failures": consecutive,
        "status": "failure",
        "error_summary": error[:2000],
        **(extra or {}),
    }
    logger.error("Source %s failed (%s consecutive): %s", source, consecutive, error)
    repo.record_source_health(payload)


def record_parser_anomaly(repo: JobRepository, source: str, missing_fields: list[str]) -> None:
    """Log parser gaps without flipping the source into consecutive failure."""
    if not missing_fields:
        return
    existing = next((row for row in repo.list_source_health() if row.get("source") == source), {})
    summary = f"parser_missing_critical_fields:{','.join(missing_fields)}"
    payload = {
        "source": source,
        "status": existing.get("status") or "degraded",
        "consecutive_failures": int(existing.get("consecutive_failures") or 0),
        "error_summary": summary[:2000],
        "jobs_seen": existing.get("jobs_seen"),
        "last_success": existing.get("last_success"),
        "updated_at": utcnow(),
    }
    if existing.get("status") == "success":
        payload["status"] = "degraded"
    logger.warning("Source %s parser anomaly: %s", source, summary)
    repo.record_source_health(payload)
