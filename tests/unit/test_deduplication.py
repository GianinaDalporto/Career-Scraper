from job_scout.models.enums import SourcePreference
from job_scout.models.job import JobSourceRef
from job_scout.services.deduplication import DuplicateIndex
from tests.conftest import canonical_job


def _ref(url: str, source="board", pref=SourcePreference.AGGREGATOR, job_id="1") -> JobSourceRef:
    return JobSourceRef(
        source_name=source,
        source_job_id=job_id,
        source_url=url,
        direct_employer_url=None,
        source_preference=pref,
    )


def test_exact_duplicate_same_url():
    idx = DuplicateIndex()
    a = canonical_job()
    b = canonical_job()
    idx.add(a, _ref("https://example.com/jobs/1", job_id="1"))
    merged = idx.add(b, _ref("https://example.com/jobs/1", source="other", job_id="99"))
    assert len(idx.jobs) == 1
    assert "duplicate_merged" in merged.flags


def test_different_urls_same_fingerprint():
    idx = DuplicateIndex()
    a = canonical_job()
    b = canonical_job(apply_url="https://aggregator.example/x")
    idx.add(a, _ref("https://careers.jacobs.com/job/1", source="greenhouse", pref=SourcePreference.EMPLOYER_ATS))
    idx.add(b, _ref("https://aggregator.example/x", source="remoteok", pref=SourcePreference.AGGREGATOR, job_id="2"))
    assert len(idx.jobs) == 1


def test_slightly_different_titles_same_company():
    idx = DuplicateIndex()
    a = canonical_job(title="Senior Mechanical Engineer")
    b = canonical_job(title="Sr Mechanical Engineer", canonical_fingerprint="other-fp")
    idx.add(a, _ref("https://a.example/1", job_id="a"))
    idx.add(b, _ref("https://b.example/2", source="agg", job_id="b"))
    assert len(idx.jobs) == 1


def test_same_title_different_city_not_merged():
    idx = DuplicateIndex()
    a = canonical_job(city="Cape Town", canonical_fingerprint="fp-ct", apply_url="https://example.com/ct")
    b = canonical_job(
        city="Johannesburg",
        canonical_fingerprint="fp-jhb",
        location_text="Johannesburg",
        apply_url="https://example.com/jhb",
        description="Different requisition for Johannesburg plant mechanical design.",
    )
    idx.add(a, _ref("https://a.example/1", job_id="a"))
    idx.add(b, _ref("https://b.example/2", job_id="b"))
    assert len(idx.jobs) == 2


def test_same_title_company_different_requisition_same_city_fingerprint():
    idx = DuplicateIndex()
    a = canonical_job()
    b = canonical_job()
    idx.add(a, _ref("https://ats.example/req-1", source="greenhouse", job_id="req-1", pref=SourcePreference.EMPLOYER_ATS))
    idx.add(b, _ref("https://ats.example/req-2", source="greenhouse", job_id="req-2", pref=SourcePreference.EMPLOYER_ATS))
    # Same fingerprint (company+title+city+country+mode) is treated as the same requisition/repost.
    assert len(idx.jobs) == 1


def test_employer_preferred_over_aggregator():
    idx = DuplicateIndex()
    agg = canonical_job(direct_employer_url=None, apply_url="https://board.example/1")
    emp = canonical_job(direct_employer_url="https://careers.jacobs.com/job/1", apply_url="https://careers.jacobs.com/job/1")
    idx.add(agg, _ref("https://board.example/1", pref=SourcePreference.AGGREGATOR))
    merged = idx.add(
        emp,
        _ref(
            "https://careers.jacobs.com/job/1",
            source="greenhouse",
            pref=SourcePreference.EMPLOYER_ATS,
            job_id="gh-1",
        ),
    )
    assert merged.direct_employer_url == "https://careers.jacobs.com/job/1"


def test_employer_outrank_keeps_index_fingerprint():
    """Regression: merge must not upsert a second jobs row under the incoming fingerprint."""
    idx = DuplicateIndex()
    agg = canonical_job(canonical_fingerprint="fp-agg", apply_url="https://board.example/same")
    emp = canonical_job(
        canonical_fingerprint="fp-emp",
        apply_url="https://board.example/same",
        direct_employer_url="https://careers.example/job/1",
    )
    idx.add(agg, _ref("https://board.example/same", pref=SourcePreference.AGGREGATOR))
    merged = idx.add(
        emp,
        _ref(
            "https://board.example/same",
            source="greenhouse",
            pref=SourcePreference.EMPLOYER_ATS,
            job_id="gh-1",
        ),
    )
    assert len(idx.jobs) == 1
    assert merged.canonical_fingerprint == "fp-agg"
    assert "fp-emp" not in idx.jobs
    assert merged.direct_employer_url == "https://careers.example/job/1"


def test_changed_salary_merges_published_value():
    from decimal import Decimal

    from job_scout.models.job import SalarySnapshot

    idx = DuplicateIndex()
    old = canonical_job(salary=SalarySnapshot(published=False))
    new = canonical_job(salary=SalarySnapshot(published=True, raw_text="R90,000 pm", min_monthly=Decimal("90000"), currency="ZAR"))
    idx.add(old, _ref("https://a.example/1"))
    merged = idx.add(new, _ref("https://b.example/1", source="other", job_id="2"))
    assert merged.salary.published is True
