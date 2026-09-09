from job_scout.models.enums import FitCategory, WorkMode
from job_scout.services.scoring import score_job
from tests.conftest import canonical_job


def test_elementary_teacher_scores_high():
    job = canonical_job(
        title="Elementary Teacher — Grade 3",
        description="Primary classroom teacher for grades 1-5. Literacy, numeracy, lesson planning, classroom management, TEFL welcome.",
        location_text="Austin, TX",
        city="Austin",
        region="TX",
        country_code="US",
        work_mode=WorkMode.ONSITE,
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score >= 70
    assert scored.fit_category in {FitCategory.GOOD, FitCategory.STRONG, FitCategory.EXCEPTIONAL, FitCategory.POSSIBLE}
    assert scored.fit_reasons


def test_surgeon_scores_low():
    job = canonical_job(
        title="Consultant Surgeon",
        company="City Hospital",
        description="Perform surgery, clinical audits, theatre lists. Medical council registration required.",
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score < 60
    assert scored.fit_category == FitCategory.LOW


def test_accountant_scores_low():
    job = canonical_job(
        title="Senior Accountant",
        description="Prepare IFRS financial statements, tax returns and statutory audits.",
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score < 60


def test_senior_java_architect_penalised():
    job = canonical_job(
        title="Principal Software Engineer / Java Architect",
        description="Deep CS background, distributed systems architect, Java, Kubernetes platform, compiler internals.",
        work_mode=WorkMode.REMOTE,
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score < 70


def test_admin_assistant_can_score():
    job = canonical_job(
        title="Administrative Assistant",
        description="School office administrative assistant, scheduling, Microsoft Office, front desk, parent communication.",
        location_text="Dallas, TX",
        city="Dallas",
        region="TX",
        country_code="US",
        work_mode=WorkMode.ONSITE,
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score >= 45
    assert not any("Mechanical" in r or "Chief Engineer" in r for r in scored.fit_reasons)


def test_spanish_teacher_scores_low():
    job = canonical_job(
        title="Spanish Immersion Teacher — Grade 3",
        description="Spanish bilingual elementary classroom, public school, K-12 district.",
        location_text="Austin, TX",
        city="Austin",
        region="TX",
        country_code="US",
        work_mode=WorkMode.ONSITE,
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score < 60


def test_supply_chain_scores_low():
    job = canonical_job(
        title="Supply Chain Coordinator",
        description="Logistics and warehouse fulfillment for an edtech elementary school curriculum kit program.",
        location_text="Houston, TX",
        city="Houston",
        region="TX",
        country_code="US",
        work_mode=WorkMode.ONSITE,
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score < 60


def test_online_tutor_scores_reasonably():
    job = canonical_job(
        title="Online Tutor — Elementary Reading",
        description="Virtual online tutor for grades 1-5 literacy. Work from home. Google Classroom.",
        location_text="United States",
        country_code="US",
        work_mode=WorkMode.REMOTE,
    )
    scored = score_job(job)
    assert scored.fit_score is not None and scored.fit_score >= 55
