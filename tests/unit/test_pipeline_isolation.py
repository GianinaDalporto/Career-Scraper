from job_scout.adapters.base import SourceAdapter
from job_scout.models.enums import PipelineName, SourceType, WorkMode
from job_scout.models.job import RawJobRecord
from job_scout.pipelines.common import run_pipeline
from job_scout.services.database import InMemoryJobRepository


class BoomAdapter(SourceAdapter):
    source_name = "boom"
    source_type = SourceType.API

    def fetch_jobs(self):
        raise RuntimeError("source down")


class OkAdapter(SourceAdapter):
    source_name = "ok"
    source_type = SourceType.API

    def fetch_jobs(self):
        yield RawJobRecord(
            source_name="ok",
            source_type=SourceType.API,
            source_job_id="1",
            source_url="https://example.com/ok",
            title="Elementary Teacher",
            company="Sunshine Academy",
            description_text="Fully remote worldwide online elementary tutoring and ESL lessons.",
            location_text="Worldwide",
            work_mode_hint="remote",
            apply_url="https://example.com/ok",
        )


def test_failed_source_does_not_abort_pipeline():
    repo = InMemoryJobRepository()
    stats = run_pipeline(
        pipeline=PipelineName.REMOTE,
        adapters=[BoomAdapter(), OkAdapter()],
        repo=repo,
        expected_work_mode=WorkMode.REMOTE,
    )
    assert stats.sources_failed == 1
    assert stats.raw_jobs >= 1
    assert any(not j.rejected for j in repo.jobs.values())
