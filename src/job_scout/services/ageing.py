"""Do not delete history; mark inactive when closed or repeatedly missing."""

from __future__ import annotations

from job_scout.services.database import JobRepository


def apply_ageing(repo: JobRepository) -> int:
    return repo.expire_jobs()
