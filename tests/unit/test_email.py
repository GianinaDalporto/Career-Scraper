from job_scout.models.enums import FitCategory, WorkMode
from job_scout.services.email_digest import render_digest_html, salary_label, select_digest_jobs, send_resend
from tests.conftest import canonical_job


def test_salary_label_remote_missing():
    job = canonical_job(work_mode=WorkMode.REMOTE)
    job.salary.published = False
    assert "Not published — allowed because role is fully remote" in salary_label(job)


def test_salary_label_hourly_part_time():
    from job_scout.services.salary import parse_salary_text

    job = canonical_job(work_mode=WorkMode.REMOTE, title="Clean Energy Mechanical Design Engineer")
    job.salary = parse_salary_text(
        "USD 80-130 per hour",
        context="±15 hours a week remote contract",
    )
    label = salary_label(job)
    assert "per hour" in label
    assert "15 hours/week" in label
    assert "40" not in label


def test_select_skips_already_notified_unchanged_from_main_list():
    from job_scout.utils.dates import utcnow

    fresh = canonical_job(title="New Mechanical Engineer", canonical_fingerprint="new-1")
    fresh.fit_score = 85
    fresh.fit_category = FitCategory.STRONG
    stale = canonical_job(title="Old Mechanical Engineer", canonical_fingerprint="old-1")
    stale.fit_score = 85
    stale.fit_category = FitCategory.STRONG
    stale.last_notified_at = utcnow()
    selection = select_digest_jobs([fresh, stale], previous_by_fp={"old-1": stale})
    fps = {j.canonical_fingerprint for j in selection.jobs}
    assert "new-1" in fps
    assert "old-1" not in fps
    assert selection.summary["new"] == 1
    assert selection.summary["returning"] == 1
    assert selection.returning[0].canonical_fingerprint == "old-1"


def test_html_has_three_sections_in_order():
    remote = canonical_job(work_mode=WorkMode.REMOTE, title="Remote PM", canonical_fingerprint="r")
    remote.fit_score = 88
    remote.fit_category = FitCategory.STRONG
    remote.apply_url = "https://example.com/remote"
    hybrid = canonical_job(work_mode=WorkMode.HYBRID, title="Hybrid ME", canonical_fingerprint="h")
    hybrid.fit_score = 80
    hybrid.fit_category = FitCategory.STRONG
    hybrid.apply_url = "https://example.com/hybrid"
    onsite = canonical_job(work_mode=WorkMode.ONSITE, title="Onsite ME", canonical_fingerprint="o")
    onsite.fit_score = 90
    onsite.fit_category = FitCategory.EXCEPTIONAL
    onsite.apply_url = "https://example.com/onsite"
    selection = select_digest_jobs([remote, hybrid, onsite])
    html = render_digest_html(
        selection,
        health={
            "sources_ok": 3,
            "sources_failed": 0,
            "last_successful_scrape": "now",
            "jobs_found": 100,
            "jobs_discarded": 40,
        },
    )
    r = html.find("REMOTE")
    h = html.find("HYBRID")
    o = html.find("ON-SITE")
    assert r < h < o
    assert "Total found" in html or "Found (recent" in html
    assert "Discarded" in html
    assert "Perfect match" in html
    assert "#1d4ed8" in html  # total found blue
    assert "#0f766e" in html  # new teal
    assert 'href="https://example.com/remote"' in html
    assert "View / apply" in html
    assert "NEW" in html
    assert "viewport" in html
    assert "Mechanical design" in html or "pipelines" in html


def test_job_excerpt_strips_html():
    from job_scout.services.email_digest import job_excerpt

    dirty = canonical_job(
        description=(
            '<div class="content-intro"><p><span style="font-family: verdana">'
            "At MacKay, we believe great people are the foundation.</span></p></div>"
        ),
    )
    blurb = job_excerpt(dirty, max_chars=220)
    assert "<div" not in blurb
    assert "font-family" not in blurb
    assert "At MacKay" in blurb


def test_job_excerpt_is_short():
    from job_scout.services.email_digest import job_excerpt

    long = canonical_job(
        description=" ".join(["Mechanical design for dams and pipelines."] * 20),
    )
    blurb = job_excerpt(long, max_chars=220)
    assert blurb.endswith("…")
    assert len(blurb) <= 230
    assert "Mechanical design" in blurb


def test_returning_section_lists_seen_before():
    from job_scout.utils.dates import utcnow

    seen = canonical_job(title="Seen Civil Engineer", canonical_fingerprint="seen-1")
    seen.fit_score = 81
    seen.fit_category = FitCategory.STRONG
    seen.last_notified_at = utcnow()
    seen.apply_url = "https://example.com/seen"
    selection = select_digest_jobs([seen], previous_by_fp={"seen-1": seen})
    html = render_digest_html(
        selection,
        health={"sources_ok": 1, "sources_failed": 0, "jobs_found": 1, "jobs_discarded": 0},
    )
    assert "STILL OPEN" in html
    assert "SEEN BEFORE" in html
    assert 'href="https://example.com/seen"' in html


def test_possible_score_included_in_digest():
    possible = canonical_job(title="Possible Civil Engineer", canonical_fingerprint="p60")
    possible.fit_score = 65
    possible.fit_category = FitCategory.POSSIBLE
    possible.apply_url = "https://example.com/possible"
    selection = select_digest_jobs([possible], min_category=FitCategory.POSSIBLE)
    assert selection.summary["possible"] == 1
    assert selection.jobs[0].canonical_fingerprint == "p60"
    html = render_digest_html(
        selection,
        health={"sources_ok": 1, "sources_failed": 0, "jobs_found": 10, "jobs_discarded": 2},
    )
    assert "Possible" in html
    assert "Possible Civil Engineer" in html


def test_send_resend_posts_to_api(monkeypatch):
    from job_scout.config.settings import Settings

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "re_test"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://api.resend.com/emails"
            assert headers["Authorization"] == "Bearer re_key"
            assert json["to"] == ["you@example.com"]
            assert json["from"] == "Job Scout <onboarding@resend.dev>"
            return FakeResponse()

    monkeypatch.setattr("job_scout.services.email_digest.httpx.Client", FakeClient)
    settings = Settings(
        resend_api_key="re_key",
        resend_from="Job Scout <onboarding@resend.dev>",
        digest_to="you@example.com",
    )
    assert send_resend("Subject", "<p>Hi</p>", settings)["id"] == "re_test"
