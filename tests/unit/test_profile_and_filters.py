from decimal import Decimal

from job_scout.config.settings import load_profile, load_salary_policy
from job_scout.models.enums import RemoteScope, WorkMode
from job_scout.services.eligibility import salary_decision
from job_scout.services.normalisation import normalise_job
from job_scout.pipelines.common import is_family_relevant
from tests.conftest import raw_job


def test_profile_contains_nina_families():
    profile = load_profile()
    families = profile["job_families"]
    assert "primary_teaching" in families
    assert "Elementary Teacher" in families["primary_teaching"]["titles"]
    assert "admin_assistant" in families
    assert profile["geographic"]["remote"]["reject_us_only"] is False
    assert profile["geographic"]["onsite_hybrid_countries"] == ["US"]
    assert "TX" in profile["geographic"]["preferred_us_states"]


def test_onsite_without_salary_flagged_not_rejected():
    policy = load_salary_policy()
    job = normalise_job(raw_job(salary_text=None, work_mode_hint="onsite", location_text="Austin, TX"))
    job.salary.published = False
    decision = salary_decision(WorkMode.ONSITE, job.salary, policy)
    assert decision.accepted is True
    assert "onsite_salary_not_published_flagged" in decision.flags


def test_onsite_below_floor_rejected():
    policy = load_salary_policy()
    snap = normalise_job(
        raw_job(salary_text="$1,000 per month", work_mode_hint="onsite", location_text="Dallas, TX")
    ).salary
    decision = salary_decision(WorkMode.ONSITE, snap, policy)
    assert decision.accepted is False
    assert any("salary_below_floor" in r for r in decision.reasons)


def test_remote_missing_salary_allowed():
    policy = load_salary_policy()
    decision = salary_decision(WorkMode.REMOTE, normalise_job(raw_job(salary_text=None)).salary, policy)
    assert decision.accepted is True


def test_family_matches_elementary_and_admin():
    profile = load_profile()
    assert is_family_relevant("Elementary Teacher - Grade 3", "literacy and numeracy", profile)
    assert is_family_relevant("Administrative Assistant", "school office scheduling", profile)
    assert not is_family_relevant("Mechanical Engineer", "pipeline design dams", profile)
    assert not is_family_relevant("Spanish Teacher - Grade 3", "elementary Spanish immersion", profile)
    assert not is_family_relevant("Supply Chain Clerk", "warehouse shipping for school district", profile)
    assert not is_family_relevant(
        "Customer Success Manager",
        "Support classroom teachers and learning experience platforms in elementary schools",
        profile,
    )


def test_us_only_remote_accepted_for_nina():
    from job_scout.services.eligibility import geographic_decision
    from job_scout.models.job import GeoSnapshot, MobilityFlags, NormalisedJobRecord, SalarySnapshot
    from job_scout.models.enums import SourcePreference, SourceType
    from job_scout.models.job import RawJobRecord

    profile = load_profile()
    raw = RawJobRecord(
        source_name="t",
        source_type=SourceType.API,
        source_job_id="1",
        source_url="https://example.com/1",
        title="Online ESL Tutor",
        company="TutorCo",
        source_preference=SourcePreference.AGGREGATOR,
    )
    job = NormalisedJobRecord(
        raw=raw,
        title="Online ESL Tutor",
        company="TutorCo",
        description="Remote US residents",
        work_mode=WorkMode.REMOTE,
        geo=GeoSnapshot(remote_scope=RemoteScope.US_ONLY, remote_eligibility_unknown=False),
        salary=SalarySnapshot(),
        mobility=MobilityFlags(),
        fingerprint="x",
    )
    decision = geographic_decision(job, profile)
    assert decision.accepted is True
