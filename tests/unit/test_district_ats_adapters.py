from pathlib import Path

from job_scout.adapters.ats.applitrack import AppliTrackAdapter, extract_applitrack_jobs
from job_scout.adapters.ats.eightfold import EightfoldAdapter
from job_scout.models.job import RawJobRecord

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _assert_raw(job: RawJobRecord) -> None:
    assert job.source_name
    assert job.source_job_id
    assert job.source_url
    assert job.title
    assert job.apply_url or job.source_url


def test_eightfold_parser_from_fixture():
    import json

    payload = json.loads((FIXTURES / "eightfold" / "houstonisd_jobs.json").read_text(encoding="utf-8"))
    adapter = EightfoldAdapter()
    jobs = []
    for item in payload["positions"]:
        item = {
            **item,
            "_company": "Houston ISD",
            "_tenant": "houstonisd.org",
            "_base_url": "https://apply.houstonisd.org",
        }
        jobs.append(adapter.parse_job(item))
    assert len(jobs) >= 1
    for job in jobs:
        _assert_raw(job)
        assert job.company == "Houston ISD"
        assert "houstonisd" in job.source_url.lower() or "apply.houstonisd" in (job.apply_url or "")
        assert job.title


def test_applitrack_extract_and_parse_fixture():
    html = (FIXTURES / "applitrack" / "fortworth_output_sample.html").read_text(encoding="utf-8")
    extracted = extract_applitrack_jobs(html)
    assert len(extracted) == 2
    assert extracted[0]["id"] == "7345"
    assert "Teacher" in extracted[0]["title"]
    assert extracted[0]["location"] == "Fort Worth, TX"
    assert extracted[1]["id"] == "8001"
    assert "Administrative Assistant" in extracted[1]["title"]

    adapter = AppliTrackAdapter()
    jobs = [
        adapter.parse_job(
            {
                **item,
                "_company": "Fort Worth ISD",
                "_slug": "fortworth",
                "_location_hint": "Fort Worth, TX, United States",
            }
        )
        for item in extracted
    ]
    for job in jobs:
        _assert_raw(job)
        assert job.company == "Fort Worth ISD"
        assert "applitrack.com/fortworth" in job.apply_url
        assert "AppliTrackJobId=" in job.apply_url
    assert jobs[0].work_mode_hint == "onsite"
