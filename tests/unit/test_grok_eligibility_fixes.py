from job_scout.config.settings import load_profile
from job_scout.models.enums import SourcePreference, SourceType, WorkMode
from job_scout.models.job import RawJobRecord
from job_scout.pipelines.common import is_family_relevant
from job_scout.services.geo import country_from_text, geo_from_raw
from job_scout.services.work_mode import classify_work_mode


def test_family_matches_primary_titles():
    profile = load_profile()
    assert is_family_relevant("Elementary Teacher", "Grade 4 classroom", profile)
    assert is_family_relevant("ESL Teacher", "TEFL online lessons", profile)


def test_unknown_not_coerced_via_remote_board_hint_with_city():
    mode = classify_work_mode(
        title="Elementary Teacher",
        description="Teach literacy and numeracy in a brick-and-mortar school.",
        location="Cape Town, South Africa",
        source_hint="remote",
    )
    assert mode == WorkMode.UNKNOWN


def test_us_city_state_is_onsite():
    mode = classify_work_mode(
        title="Grade 2 Teacher",
        description="Classroom teaching for elementary students.",
        location="Austin, TX",
        source_hint=None,
    )
    assert mode == WorkMode.ONSITE
    assert country_from_text("Austin, TX") == "US"


def test_dpsa_head_office_still_scoped():
    assert country_from_text("Head Office") is None
    raw = RawJobRecord(
        source_name="dpsa_circular",
        source_type=SourceType.HTML,
        source_job_id="1",
        source_url="https://www.dpsa.gov.za/x.pdf#post-1",
        title="Teacher",
        company="Department of Basic Education",
        location_text="Head Office",
        source_preference=SourcePreference.GOVERNMENT,
    )
    assert geo_from_raw(raw, "").country_code == "ZA"
