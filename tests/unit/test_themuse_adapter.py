from job_scout.adapters.remote.themuse import TheMuseAdapter
from job_scout.models.job import RawJobRecord


def _assert_raw(job: RawJobRecord) -> None:
    assert job.source_name
    assert job.source_job_id
    assert job.source_url
    assert job.title
    assert job.apply_url or job.source_url


def test_themuse_parser():
    job = TheMuseAdapter().parse_job(
        {
            "id": 21589580,
            "name": "Administrative Assistant",
            "company": {"id": 1, "name": "Example Schools"},
            "contents": "<p>Support an elementary campus office.</p>",
            "locations": [{"name": "Tampa, FL"}],
            "publication_date": "2026-08-16T18:53:29Z",
            "refs": {
                "landing_page": "https://www.themuse.com/jobs/example/administrative-assistant-d250f1"
            },
            "categories": [{"name": "Education"}],
            "levels": [{"name": "Entry Level"}],
        }
    )
    _assert_raw(job)
    assert job.company == "Example Schools"
    assert "Tampa" in (job.location_text or "")
    assert "themuse.com" in (job.apply_url or "")
