"""Vacancy identity, AppliTrack URLs, and district geography regressions."""

from __future__ import annotations

from pathlib import Path

from job_scout.config.settings import load_profile, load_salary_policy
from job_scout.models.enums import SourcePreference, SourceType, WorkMode
from job_scout.models.job import JobSourceRef
from job_scout.pipelines.common import is_family_relevant
from job_scout.services.deduplication import DuplicateIndex, canonical_url, identity_query_values
from job_scout.services.eligibility import apply_hard_filters
from job_scout.services.geo import geo_from_raw, is_ambiguous_location
from job_scout.services.normalisation import fingerprint, normalise_job, requisition_for_fingerprint
from job_scout.adapters.ats.applitrack import AppliTrackAdapter, extract_applitrack_detail_text
from tests.conftest import canonical_job, raw_job

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_canonical_url_keeps_applitrack_job_id_strips_utm():
    url = (
        "https://www.applitrack.com/fortworth/onlineapp/jobpostings/view.asp"
        "?utm_source=email&AppliTrackJobId=7345&fbclid=abc"
    )
    canon = canonical_url(url)
    assert "applitrackjobid=7345" in canon
    assert "utm_source" not in canon
    assert "fbclid" not in canon
    assert identity_query_values(url) == frozenset({("applitrackjobid", "7345")})


def test_different_applitrack_ids_do_not_merge():
    idx = DuplicateIndex()
    base = "https://www.applitrack.com/fortworth/onlineapp/jobpostings/view.asp"
    a = canonical_job(
        title="Elementary Teacher",
        company="Fort Worth ISD",
        city="Fort Worth",
        country_code="US",
        location_text="To Be Determined",
        canonical_fingerprint=fingerprint(
            "Fort Worth ISD", "Elementary Teacher", "Fort Worth", "US", "onsite", "7345"
        ),
        apply_url=f"{base}?AppliTrackJobId=7345",
        description="Elevate campus elementary teacher posting A.",
    )
    b = canonical_job(
        title="Elementary Teacher",
        company="Fort Worth ISD",
        city="Fort Worth",
        country_code="US",
        location_text="To Be Determined",
        canonical_fingerprint=fingerprint(
            "Fort Worth ISD", "Elementary Teacher", "Fort Worth", "US", "onsite", "8001"
        ),
        apply_url=f"{base}?AppliTrackJobId=8001",
        description="Elevate campus elementary teacher posting B.",
    )
    idx.add(
        a,
        JobSourceRef(
            source_name="applitrack:fortworth",
            source_job_id="7345",
            source_url=a.apply_url or "",
            direct_employer_url=a.apply_url,
            source_preference=SourcePreference.EMPLOYER_CAREER,
        ),
    )
    idx.add(
        b,
        JobSourceRef(
            source_name="applitrack:fortworth",
            source_job_id="8001",
            source_url=b.apply_url or "",
            direct_employer_url=b.apply_url,
            source_preference=SourcePreference.EMPLOYER_CAREER,
        ),
    )
    assert len(idx.jobs) == 2
    assert canonical_url(a.apply_url) != canonical_url(b.apply_url)


def test_identical_title_different_requisitions_stay_separate():
    fp1 = fingerprint("KIPP", "Elementary Teacher", "Dallas", "US", "onsite", "111")
    fp2 = fingerprint("KIPP", "Elementary Teacher", "Dallas", "US", "onsite", "222")
    assert fp1 != fp2


def test_genuine_cross_source_duplicate_still_merges():
    """Same employer career URL seen from an aggregator must still collapse."""
    idx = DuplicateIndex()
    url = "https://careers.example.com/jobs/elem-42"
    a = canonical_job(
        title="Elementary Teacher — Grade 3",
        company="Example ISD",
        city="Austin",
        country_code="US",
        apply_url=url,
        canonical_fingerprint=fingerprint(
            "Example ISD", "Elementary Teacher — Grade 3", "Austin", "US", "onsite", "elem-42"
        ),
        description="Grade 3 elementary classroom teacher literacy numeracy parent communication.",
    )
    b = canonical_job(
        title="Elementary Teacher — Grade 3",
        company="Example ISD",
        city="Austin",
        country_code="US",
        apply_url=url,
        # Aggregator omits requisition in fingerprint.
        canonical_fingerprint=fingerprint(
            "Example ISD", "Elementary Teacher — Grade 3", "Austin", "US", "onsite", None
        ),
        description="Grade 3 elementary classroom teacher literacy numeracy parent communication.",
    )
    idx.add(
        a,
        JobSourceRef(
            source_name="applitrack:example",
            source_job_id="elem-42",
            source_url=url,
            direct_employer_url=url,
            source_preference=SourcePreference.EMPLOYER_CAREER,
        ),
    )
    idx.add(
        b,
        JobSourceRef(
            source_name="remoteok",
            source_job_id="agg-9",
            source_url=url,
            direct_employer_url=None,
            source_preference=SourcePreference.AGGREGATOR,
        ),
    )
    assert len(idx.jobs) == 1
    assert "duplicate_merged" in list(idx.jobs.values())[0].flags


def test_ambiguous_campus_location_keeps_text_and_resolves_hint():
    assert is_ambiguous_location("To Be Determined")
    raw = raw_job(
        source_name="applitrack:fortworth",
        source_type=SourceType.HTML,
        source_job_id="7345",
        source_url="https://www.applitrack.com/fortworth/onlineapp/jobpostings/view.asp?AppliTrackJobId=7345",
        title="Elementary Teacher - Grade 3",
        company="Fort Worth ISD",
        description_text=(
            "Primary classroom teacher for grades 1-5. Literacy, numeracy, "
            "lesson planning, classroom management, TEFL welcome. Public school district."
        ),
        location_text="To Be Determined",
        work_mode_hint="onsite",
        salary_text=None,
        apply_url="https://www.applitrack.com/fortworth/onlineapp/jobpostings/view.asp?AppliTrackJobId=7345",
        source_preference=SourcePreference.EMPLOYER_CAREER,
        raw_payload={
            "location_hint": "Fort Worth, TX, United States",
            "posted_location": "To Be Determined",
        },
    )
    geo = geo_from_raw(raw, raw.description_text or "")
    assert geo.location_text == "To Be Determined"
    assert geo.country_code == "US"
    assert geo.region == "TX"
    assert geo.city and "fort worth" in geo.city.lower()

    normalised = normalise_job(raw)
    assert normalised.work_mode == WorkMode.ONSITE
    assert requisition_for_fingerprint(raw) == "7345"
    assert is_family_relevant(normalised.title, normalised.description, load_profile())
    decision = apply_hard_filters(
        normalised,
        profile=load_profile(),
        policy=load_salary_policy(),
    )
    assert decision.accepted is True
    assert "preferred_us_state" in decision.flags


def test_applitrack_parse_preserves_posted_location_and_hint():
    job = AppliTrackAdapter().parse_job(
        {
            "id": "8001",
            "title": "Administrative Assistant – Elementary",
            "location": "To Be Determined",
            "date_posted": "9/1/2026",
            "closing": "Open Until Filled",
            "_company": "Fort Worth ISD",
            "_slug": "fortworth",
            "_location_hint": "Fort Worth, TX, United States",
        }
    )
    assert job.location_text == "To Be Determined"
    assert job.raw_payload["location_hint"] == "Fort Worth, TX, United States"
    assert job.raw_payload["posted_location"] == "To Be Determined"
    assert "AppliTrackJobId=8001" in (job.apply_url or "")


def test_applitrack_detail_extractor_on_fixture_snippet():
    html = """
    document.write('<p><strong>Position Purpose</strong></p><p>This position serves at an
    Elevate campus and focuses on accelerating language acquisition and academic performance
    through differentiated instruction for elementary learners.</p>
    <p><strong>Qualifications</strong></p><ul><li>Bachelor of Education preferred</li></ul>
    Email To A Friend');
    """
    text = extract_applitrack_detail_text(html)
    assert text
    assert "Elevate campus" in text
    assert "Bachelor of Education" in text
