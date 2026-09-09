from job_scout.orchestration.health_check import run_health
from job_scout.services.database import (
    JOBS_OPTIONAL_COLUMNS,
    InMemoryJobRepository,
    filter_job_payload,
)
from tests.conftest import canonical_job
from job_scout.models.job import JobSourceRef
from job_scout.models.enums import SourcePreference
from job_scout.utils.dates import utcnow


def test_memory_health():
    ping = run_health(memory=True)
    assert ping["ok"] is True


def test_upsert_and_digest_candidates():
    repo = InMemoryJobRepository()
    job = canonical_job()
    job.fit_score = 80
    from job_scout.models.enums import FitCategory

    job.fit_category = FitCategory.STRONG
    repo.upsert_job(
        job,
        JobSourceRef(
            source_name="t",
            source_job_id="1",
            source_url="https://example.com/1",
            source_preference=SourcePreference.AGGREGATOR,
        ),
    )
    found = repo.list_digest_candidates(None, 70)
    assert found


def test_filter_job_payload_omits_optional_when_schema_unknown():
    payload = {
        "title": "Engineer",
        "apply_url": "https://example.com/a",
        "rejected": True,
        "direct_employer_url": "https://example.com/b",
        "digest_pending_update": True,
        "rejection_reasons": ["salary"],
    }
    filtered = filter_job_payload(payload, frozenset())
    assert filtered == {"title": "Engineer"}
    assert JOBS_OPTIONAL_COLUMNS.isdisjoint(filtered)


def test_filter_job_payload_keeps_present_optional_columns():
    payload = {
        "title": "Engineer",
        "apply_url": "https://example.com/a",
        "rejected": False,
        "rejection_reasons": [],
        "digest_pending_update": False,
        "direct_employer_url": None,
    }
    columns = frozenset({"title", "apply_url", "rejected", "rejection_reasons"})
    filtered = filter_job_payload(payload, columns)
    assert filtered["apply_url"] == "https://example.com/a"
    assert "rejected" in filtered
    assert "digest_pending_update" not in filtered
    assert "direct_employer_url" not in filtered
    assert set(filtered) <= columns


def test_job_row_omits_apply_url_without_column():
    from job_scout.services.database import _job_row

    job = canonical_job(apply_url="https://example.com/apply")
    # When discovery succeeded with a narrow column set, only those keys are sent.
    row = _job_row(
        job,
        None,
        utcnow(),
        columns=frozenset({"title", "canonical_fingerprint", "active", "work_mode", "remote_scope"}),
    )
    assert "apply_url" not in row
    assert "rejected" not in row
    assert row["title"] == job.title
    assert set(row) <= {
        "title",
        "canonical_fingerprint",
        "active",
        "work_mode",
        "remote_scope",
    }