from job_scout.adapters.ats.greenhouse import GreenhouseAdapter
from job_scout.adapters.mocks import MockApiAdapter, MockHtmlAdapter, MockRssAdapter
from job_scout.adapters.regional.reliefweb import ReliefWebAdapter
from job_scout.adapters.remote.jobicy import JobicyAdapter
from job_scout.adapters.remote.remote1stjobs import Remote1stJobsAdapter
from job_scout.adapters.remote.remoteok import RemoteOKAdapter
from job_scout.adapters.remote.remotive import RemotiveAdapter
from job_scout.models.job import RawJobRecord


def _assert_raw(job: RawJobRecord):
    assert job.source_name
    assert job.source_job_id
    assert job.source_url
    assert job.title
    assert job.apply_url or job.source_url


def test_mock_adapters_share_raw_shape():
    api = list(
        MockApiAdapter(
            {
                "jobs": [
                    {
                        "id": "a1",
                        "url": "https://example.com/a1",
                        "title": "Mechanical Engineer",
                        "company": "Acme",
                        "description": "<p>Pumps</p>",
                        "location": "Worldwide",
                        "work_mode": "remote",
                        "salary": "$90,000 per year",
                    }
                ]
            }
        ).fetch_jobs()
    )
    rss = list(
        MockRssAdapter(
            {
                "jobs": [
                    {
                        "id": "r1",
                        "link": "https://example.com/r1",
                        "title": "Mechanical Engineer",
                        "company": "Acme",
                        "summary": "<p>Pumps</p>",
                        "published": "2026-01-01",
                    }
                ]
            }
        ).fetch_jobs()
    )
    html = list(
        MockHtmlAdapter(
            {
                "jobs": [
                    {
                        "id": "h1",
                        "url": "https://example.com/h1",
                        "title": "Mechanical Engineer",
                        "company": "Acme",
                        "html": "<p>Pumps</p>",
                        "location": "Cape Town",
                        "work_mode": "onsite",
                        "salary": "R80,000 pm",
                    }
                ]
            }
        ).fetch_jobs()
    )
    for job in api + rss + html:
        _assert_raw(job)
        assert set(job.model_dump().keys()) == set(api[0].model_dump().keys())


def test_remoteok_parser():
    job = RemoteOKAdapter().parse_job(
        {
            "id": "123",
            "position": "Remote Mechanical Engineer",
            "company": "PipeCo",
            "description": "<p>Pipelines</p>",
            "url": "https://remoteok.com/remote-jobs/123",
            "location": "Worldwide",
            "salary_min": 80000,
            "salary_max": 120000,
            "salary_currency": "USD",
            "date": "2026-01-02",
        }
    )
    _assert_raw(job)
    assert job.company == "PipeCo"


def test_remotive_parser():
    job = RemotiveAdapter().parse_job(
        {
            "id": 9,
            "url": "https://remotive.com/jobs/9",
            "title": "Project Manager",
            "company_name": "RemotiveCo",
            "description": "Technical project manager for water plants",
            "candidate_required_location": "Anywhere",
            "publication_date": "2026-02-01",
        }
    )
    _assert_raw(job)


def test_jobicy_parser():
    job = JobicyAdapter().parse_job(
        {
            "id": 5,
            "url": "https://jobicy.com/jobs/5",
            "jobTitle": "Automation Specialist",
            "companyName": "AutoCo",
            "jobDescription": "Workflow automation",
            "jobGeo": "Anywhere",
            "pubDate": "2026-03-01",
        }
    )
    _assert_raw(job)


def test_greenhouse_parser():
    job = GreenhouseAdapter().parse_job(
        {
            "id": 77,
            "title": "Mechanical Design Engineer",
            "absolute_url": "https://boards.greenhouse.io/stantec/jobs/77",
            "content": "<p>Dams and pipelines</p>",
            "location": {"name": "Denver, United States"},
            "_company": "Stantec",
            "_slug": "stantec",
        }
    )
    _assert_raw(job)
    assert job.direct_employer_url
    assert "title" in job.model_dump()


def test_reliefweb_parser():
    job = ReliefWebAdapter().parse_job(
        {
            "id": "https://reliefweb.int/job/1",
            "link": "https://reliefweb.int/job/1",
            "title": "WASH Engineer",
            "author": "NGO Example",
            "summary": "<div>Country: South Africa</div><p>Water infrastructure</p>",
            "published": "2026-09-01",
        }
    )
    _assert_raw(job)
    assert job.company == "NGO Example"
    assert job.location_text == "South Africa"


def test_remote1stjobs_parser():
    job = Remote1stJobsAdapter().parse_job(
        {
            "title": "Infrastructure Engineer",
            "company": "RemoteCo",
            "location": "Berlin, Remote",
            "url": "https://www.remote1stjobs.com/jobs/infra-1",
            "description": "Pipelines and remote ops",
            "created_at": "2026-09-01T00:00:00+00:00",
            "category": "Engineering",
        }
    )
    _assert_raw(job)
    assert job.work_mode_hint == "remote"
