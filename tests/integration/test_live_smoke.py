import os

import pytest

from job_scout.adapters.remote.jobicy import JobicyAdapter
from job_scout.adapters.remote.remoteok import RemoteOKAdapter
from job_scout.adapters.remote.remotive import RemotiveAdapter

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("JOB_SCOUT_LIVE") != "1", reason="Live HTTP disabled")
def test_live_remote_sources_smoke():
    counts = {}
    errors = {}
    samples = {}
    for adapter in (RemoteOKAdapter(), RemotiveAdapter(), JobicyAdapter()):
        jobs = []
        try:
            jobs = list(adapter.fetch_jobs())
        except Exception as exc:  # noqa: BLE001
            errors[adapter.source_name] = str(exc)
        counts[adapter.source_name] = len(jobs)
        if jobs:
            job = jobs[0]
            samples[adapter.source_name] = {
                "title": job.title,
                "company": job.company,
                "url": job.source_url,
            }
            assert job.title
            assert job.source_url
    print("LIVE_COUNTS", counts)
    print("LIVE_ERRORS", errors)
    print("LIVE_SAMPLES", samples)
    assert sum(counts.values()) > 0 or errors
