from job_scout.adapters.ats.smartrecruiters import SmartRecruitersAdapter, _public_job_url
from job_scout.models.enums import SourcePreference
from job_scout.models.job import CanonicalJobRecord, JobSourceRef, MobilityFlags, SalarySnapshot
from job_scout.models.enums import WorkMode
from job_scout.services.deduplication import DuplicateIndex


def test_smartrecruiters_prefers_public_url_not_api_ref():
    payload = {
        "id": "7440001",
        "name": "Water Engineer",
        "ref": "https://api.smartrecruiters.com/v1/companies/AECOM2/postings/7440001",
        "applyUrl": "https://jobs.smartrecruiters.com/AECOM2/7440001-water-engineer",
        "_slug": "AECOM2",
        "_company": "AECOM",
        "location": {"city": "Cape Town", "countryCode": "ZA"},
    }
    job = SmartRecruitersAdapter().parse_job(payload)
    assert "api.smartrecruiters.com" not in (job.apply_url or "")
    assert "jobs.smartrecruiters.com" in (job.apply_url or "")
    assert job.direct_employer_url == job.apply_url
    assert _public_job_url({"id": "9", "ref": "https://api.smartrecruiters.com/x"}, "AECOM2").endswith(
        "/AECOM2/9"
    )


def test_dpsa_shared_pdf_urls_do_not_collapse_distinct_posts():
    index = DuplicateIndex()
    pdf = "https://www.dpsa.gov.za/dpsa2g/documents/vacancies/2026/32/s.pdf"

    def make(post_id: str, title: str) -> tuple[CanonicalJobRecord, JobSourceRef]:
        url = f"{pdf}#post-{post_id}"
        job = CanonicalJobRecord(
            canonical_fingerprint=f"fp-{post_id}",
            title=title,
            company="Limpopo",
            work_mode=WorkMode.ONSITE,
            salary=SalarySnapshot(published=True, raw_text="R100000", currency="ZAR", period="annual"),
            mobility=MobilityFlags(),
            apply_url=url,
            direct_employer_url=url,
            fit_score=70,
        )
        ref = JobSourceRef(
            source_name="dpsa_circular",
            source_job_id=f"2026-{post_id}",
            source_url=url,
            direct_employer_url=url,
            source_preference=SourcePreference.GOVERNMENT,
        )
        return job, ref

    a_job, a_ref = make("32/252", "CHIEF ENGINEER, GRADE A")
    b_job, b_ref = make("32/262", "CIVIL/ STRUCTURAL ENGINEER")
    index.add(a_job, a_ref)
    index.add(b_job, b_ref)
    assert len(index.jobs) == 2
