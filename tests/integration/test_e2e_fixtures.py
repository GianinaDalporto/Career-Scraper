from job_scout.models.enums import PipelineName, WorkMode
from job_scout.pipelines.common import run_pipeline
from job_scout.adapters.mocks import MockApiAdapter
from job_scout.services.database import InMemoryJobRepository
from job_scout.services.email_digest import select_digest_jobs


def test_end_to_end_fixture_pipeline_and_digest():
    repo = InMemoryJobRepository()
    adapter = MockApiAdapter(
        {
            "enabled": True,
            "jobs": [
                {
                    "id": "1",
                    "url": "https://example.com/1",
                    "title": "Lead Mechanical Engineer",
                    "company": "WaterCo",
                    "description": "Fully remote worldwide. Dams, pipelines, pumps, QA/QC, FIDIC.",
                    "location": "Worldwide",
                    "work_mode": "remote",
                    "salary": None,
                    "date": "2026-04-01",
                },
                {
                    "id": "2",
                    "url": "https://example.com/2",
                    "title": "Consultant Surgeon",
                    "company": "Hospital",
                    "description": "Theatre lists",
                    "location": "London",
                    "work_mode": "onsite",
                    "salary": "£20,000 per month",
                },
            ],
        }
    )
    stats = run_pipeline(
        pipeline=PipelineName.REMOTE,
        adapters=[adapter],
        repo=repo,
        fx=None,
        expected_work_mode=WorkMode.REMOTE,
    )
    assert stats.raw_jobs == 2
    accepted = [j for j in repo.jobs.values() if not j.rejected and j.active]
    assert accepted
    assert accepted[0].fit_score is not None
    selection = select_digest_jobs(list(repo.jobs.values()))
    assert selection.jobs


def test_in_memory_repo_does_not_need_supabase():
    repo = InMemoryJobRepository()
    assert repo.ping()["backend"] == "memory"
