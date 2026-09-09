from job_scout.models.enums import WorkMode
from job_scout.services.work_mode import classify_work_mode


def test_fully_remote():
    assert classify_work_mode(title="Engineer", description="This role is fully remote.", location="Worldwide", source_hint=None) == WorkMode.REMOTE


def test_hybrid():
    assert classify_work_mode(title="Engineer", description="Hybrid, 3 days in office.", location="Cape Town", source_hint=None) == WorkMode.HYBRID


def test_onsite():
    assert classify_work_mode(title="Site Engineer", description="This is an on-site role at the dam.", location="Pretoria", source_hint=None) == WorkMode.ONSITE


def test_remote_sensing_is_not_wfh():
    mode = classify_work_mode(
        title="Remote sensing analyst",
        description="Work with remote sensing imagery on site at the plant.",
        location="Johannesburg",
        source_hint=None,
    )
    assert mode != WorkMode.REMOTE


def test_us_residents_only_still_remote_workmode():
    mode = classify_work_mode(
        title="Mechanical Engineer",
        description="Remote – US residents only. Work from home.",
        location="Remote – US residents only",
        source_hint="remote",
    )
    assert mode == WorkMode.REMOTE


def test_city_country_without_onsite_keyword_is_onsite():
    mode = classify_work_mode(
        title="Mechanical Engineer",
        description="Design piping systems for water treatment.",
        location="Denver, CO",
        source_hint=None,
    )
    assert mode == WorkMode.ONSITE
