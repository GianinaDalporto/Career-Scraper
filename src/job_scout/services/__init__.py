from job_scout.services.database import InMemoryJobRepository, JobRepository, build_repository
from job_scout.services.deduplication import DuplicateIndex, to_canonical
from job_scout.services.eligibility import apply_hard_filters
from job_scout.services.email_digest import build_and_maybe_send, render_digest_html, select_digest_jobs
from job_scout.services.fx import FxService, InMemoryFxStore
from job_scout.services.normalisation import normalise_job
from job_scout.services.salary import parse_salary_text
from job_scout.services.scoring import score_job

__all__ = [
    "DuplicateIndex",
    "FxService",
    "InMemoryFxStore",
    "InMemoryJobRepository",
    "JobRepository",
    "apply_hard_filters",
    "build_and_maybe_send",
    "build_repository",
    "normalise_job",
    "parse_salary_text",
    "render_digest_html",
    "score_job",
    "select_digest_jobs",
    "to_canonical",
]
