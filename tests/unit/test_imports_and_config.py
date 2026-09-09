from job_scout import __version__
from job_scout.config.settings import get_settings, load_profile, load_salary_policy, load_sources
from job_scout.services.normalisation import normalise_job
from tests.conftest import raw_job


def test_package_imports():
    assert __version__


def test_config_loads():
    settings = get_settings()
    profile = load_profile(settings)
    policy = load_salary_policy(settings)
    sources = load_sources(settings)
    assert "job_families" in profile
    assert "primary_teaching" in profile["job_families"]
    assert policy["currency_floors_monthly"]["USD"] == 2800
    assert policy["currency_floors_monthly"]["ZAR"] == 40000
    assert "remoteok" in sources["sources"]


def test_raw_job_roundtrip():
    job = normalise_job(raw_job(title="Elementary Teacher", location_text="Austin, TX"))
    assert job.title
    assert job.work_mode
    assert job.fingerprint
