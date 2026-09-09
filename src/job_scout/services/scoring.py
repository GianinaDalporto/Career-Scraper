"""Explainable 0–100 fit scoring. No paid LLM."""

from __future__ import annotations

import re
from typing import Any

from job_scout.config.settings import load_profile, load_scoring
from job_scout.models.enums import FitCategory, RemoteScope, WorkMode
from job_scout.models.job import CanonicalJobRecord, ScoreBreakdown
from job_scout.utils.text import normalise_key


def _hits(blob: str, phrases: list[str]) -> list[str]:
    found = []
    for phrase in phrases:
        key = normalise_key(phrase)
        if not key:
            continue
        if len(key) <= 3:
            if re.search(rf"\b{re.escape(key)}\b", blob):
                found.append(phrase)
        elif key in blob:
            found.append(phrase)
    return found


def _scale(hits: int, cap: int, weight: float) -> float:
    if cap <= 0:
        return 0.0
    return min(1.0, hits / cap) * weight


def category_for(score: int, scoring: dict[str, Any]) -> FitCategory:
    bands = scoring.get("categories") or {}
    for name, bounds in bands.items():
        low, high = bounds
        if low <= score <= high:
            return FitCategory(name)
    return FitCategory.LOW


def score_job(
    job: CanonicalJobRecord,
    *,
    profile: dict[str, Any] | None = None,
    scoring: dict[str, Any] | None = None,
) -> CanonicalJobRecord:
    profile = profile or load_profile()
    scoring = scoring or load_scoring()
    weights = scoring.get("weights") or {}
    blob = normalise_key(f"{job.title}\n{job.company or ''}\n{job.description}\n{job.location_text or ''}")
    title = normalise_key(job.title)
    reasons: list[str] = []
    concerns: list[str] = []
    breakdown = ScoreBreakdown()

    prof_hits = _hits(blob, scoring.get("professional_positive") or [])
    breakdown.professional_relevance = _scale(len(prof_hits), 5, float(weights.get("professional_relevance", 25)))
    if prof_hits:
        reasons.append(f"Teaching/education language matches your background: {', '.join(prof_hits[:4])}.")

    skill_hits = _hits(blob, scoring.get("skills_positive") or [])
    breakdown.skills = _scale(len(skill_hits), 4, float(weights.get("skills", 18)))
    if skill_hits:
        reasons.append(f"Required methods overlap your practice: {', '.join(skill_hits[:4])}.")

    sen_hits = _hits(blob, scoring.get("seniority_positive") or [])
    breakdown.seniority = _scale(len(sen_hits), 2, float(weights.get("seniority", 8)))
    if sen_hits:
        reasons.append(f"Seniority ({', '.join(sen_hits)}) aligns with lead / mentor teacher experience.")

    sector_hits = _hits(blob, scoring.get("sectors_high") or [])
    breakdown.sector = _scale(len(sector_hits), 3, float(weights.get("sector", 12)))
    if sector_hits:
        reasons.append(f"Sector fit: {', '.join(sector_hits[:3])}.")

    lead_hits = _hits(blob, scoring.get("leadership_positive") or [])
    breakdown.leadership_pm = _scale(len(lead_hits), 3, float(weights.get("leadership_pm", 10)))
    if lead_hits:
        reasons.append(f"Leadership/delivery overlap: {', '.join(lead_hits[:3])}.")

    digital_hits = _hits(blob, scoring.get("digital_positive") or [])
    overclaim = _hits(blob, scoring.get("digital_overclaim_penalties") or [])
    digital_weight = float(weights.get("digital_transferability", 6))
    if overclaim and not digital_hits:
        breakdown.digital_transferability = 0
        breakdown.penalties += 25
        concerns.append(
            "Advert asks for specialist software-engineering experience "
            f"({', '.join(overclaim[:3])}) beyond classroom / online-teaching tools."
        )
    else:
        breakdown.digital_transferability = _scale(len(digital_hits), 3, digital_weight)
        if overclaim:
            breakdown.penalties += 12
            concerns.append(
                f"Software specialism still listed ({', '.join(overclaim[:2])}); treat digital fit as transferable, not equivalent."
            )
        elif digital_hits:
            reasons.append(f"Online / classroom digital tools apply: {', '.join(digital_hits[:3])}.")

    ops_hits = _hits(blob, scoring.get("operations_positive") or [])
    breakdown.operations_alt = _scale(len(ops_hits), 2, float(weights.get("operations_alt", 6)))
    if ops_hits:
        reasons.append(f"School / office admin overlap: {', '.join(ops_hits[:3])}.")

    unrelated = _hits(title, scoring.get("unrelated_roles") or [])
    if not unrelated:
        unrelated = _hits(blob, scoring.get("unrelated_roles") or [])
    if unrelated:
        breakdown.penalties += 50
        concerns.append(f"Core occupation appears unrelated ({', '.join(unrelated[:2])}).")

    # Compensation above floor (already gated) — floors from salary_policy.yaml.
    from job_scout.config.settings import load_salary_policy

    policy = load_salary_policy()
    floors_cfg = policy.get("currency_floors_monthly") or {}
    comp_weight = float(weights.get("compensation", 7))
    multiple = None
    if job.salary.min_monthly and job.salary.currency:
        floor = floors_cfg.get(job.salary.currency.upper())
        if floor is not None:
            multiple = float(job.salary.min_monthly) / float(floor)
    if multiple is None and job.salary.usd_monthly:
        usd_floor = float(
            (policy.get("default_international_floor") or {}).get("amount_monthly")
            or floors_cfg.get("USD")
            or 2800
        )
        multiple = float(job.salary.usd_monthly) / usd_floor
    if multiple is not None:
        breakdown.compensation = min(comp_weight, 4.0 + max(0.0, multiple - 1.0) * 6.0)
        reasons.append("Employer-published salary meets or exceeds the configured floor.")
    elif job.work_mode == WorkMode.REMOTE and not job.salary.published:
        breakdown.compensation = 2.0
        concerns.append("Salary not published — allowed because the role is fully remote.")
    elif "onsite_salary_not_published_flagged" in job.flags:
        breakdown.compensation = 1.0
        concerns.append("Onsite/hybrid salary not published — flagged for manual review.")

    wm_boost = scoring.get("work_mode_boost") or {}
    if job.work_mode == WorkMode.REMOTE and job.remote_scope in {
        RemoteScope.WORLDWIDE,
        RemoteScope.ANYWHERE,
        RemoteScope.GLOBAL,
        RemoteScope.US_ONLY,
    }:
        breakdown.work_mode = float(wm_boost.get("remote_global", 4))
        reasons.append("Remote role with geographic scope compatible with a USA-focused search.")
    elif job.work_mode == WorkMode.REMOTE:
        breakdown.work_mode = float(wm_boost.get("remote_unknown", 2))
    elif job.work_mode == WorkMode.HYBRID:
        breakdown.work_mode = float(wm_boost.get("hybrid", 3))
    elif job.work_mode == WorkMode.ONSITE:
        breakdown.work_mode = float(wm_boost.get("onsite", 4))
    if "preferred_us_state" in job.flags:
        breakdown.work_mode += float(wm_boost.get("preferred_us_state", 6))
        reasons.append("Location is in a preferred US state.")
    elif "us_outside_preferred_states" in job.flags:
        breakdown.penalties += 4
        concerns.append("US location is outside preferred Southern / Bible Belt states.")

    notes = (job.mobility.work_authorisation_notes or "").lower()
    if job.mobility.visa_sponsorship:
        breakdown.international_mobility += float((scoring.get("mobility_boost") or {}).get("visa_sponsorship", 12))
        reasons.append("Employer states visa sponsorship is available.")
    if "j-1" in notes or "exchange visitor" in notes:
        breakdown.international_mobility += float((scoring.get("mobility_boost") or {}).get("j1_or_h1b", 10))
        reasons.append("J-1 / exchange visitor pathway is mentioned.")
    if "h-1b" in notes or "h1b" in notes:
        breakdown.international_mobility += float((scoring.get("mobility_boost") or {}).get("j1_or_h1b", 10))
        reasons.append("H-1B pathway is mentioned.")
    if "international teacher" in notes:
        breakdown.international_mobility += float(
            (scoring.get("mobility_boost") or {}).get("international_teacher_program", 10)
        )
    if job.mobility.relocation_assistance:
        breakdown.international_mobility += float((scoring.get("mobility_boost") or {}).get("relocation", 6))
        reasons.append("Relocation assistance is mentioned.")
    if job.mobility.citizenship_required:
        breakdown.international_mobility -= float((scoring.get("mobility_penalty") or {}).get("citizenship_required", 8))
        concerns.append("US citizenship is explicitly required — flagged, not auto-rejected.")
    if job.mobility.work_right_required:
        breakdown.international_mobility -= float(
            (scoring.get("mobility_penalty") or {}).get("unrestricted_work_rights", 6)
        )
        concerns.append("Existing US work authorisation is required — flagged, not auto-rejected.")
    if job.mobility.unknown:
        concerns.append("Visa/work-authorisation status is unknown — not assumed.")

    families = (profile.get("job_families") or {})
    family_hit = False
    family_weight = 0.0
    for spec in families.values():
        titles = [normalise_key(t) for t in spec.get("titles") or []]
        keywords_hit = any(normalise_key(k) in blob for k in spec.get("keywords") or [])
        title_hit = any(t and t in title for t in titles)
        if title_hit or keywords_hit:
            family_hit = True
            family_weight = max(family_weight, float(spec.get("weight") or 0.5))
    if family_hit:
        breakdown.professional_relevance = max(
            breakdown.professional_relevance,
            float(weights.get("professional_relevance", 25)) * min(1.0, family_weight),
        )
    elif breakdown.professional_relevance < 8:
        concerns.append("Title/description is only weakly related to configured job families.")

    total = (
        breakdown.professional_relevance
        + breakdown.skills
        + breakdown.seniority
        + breakdown.sector
        + breakdown.leadership_pm
        + breakdown.digital_transferability
        + breakdown.operations_alt
        + breakdown.compensation
        + breakdown.work_mode
        + max(breakdown.international_mobility, -20)
        - breakdown.penalties
    )
    score = int(max(0, min(100, round(total))))
    # Floor only for generalist primary / ESL-English / remote teaching / school admin —
    # never for bare "grade N" alone (Spanish Grade 1 Teacher used to jump to 72).
    subject_blocked = any(
        phrase in title
        for phrase in (
            "spanish",
            "french",
            "german",
            "mandarin",
            "chinese",
            "physical education",
            "pe teacher",
            "supply chain",
            "logistics",
            "warehouse",
        )
    )
    core_titles = (
        "elementary teacher",
        "primary teacher",
        "classroom teacher",
        "homeroom",
        "self-contained",
        "esl teacher",
        "ell teacher",
        "eld teacher",
        "online teacher",
        "virtual teacher",
        "remote teacher",
        "online tutor",
        "virtual tutor",
        "administrative assistant",
        "school secretary",
    )
    generalist = any(token in title for token in core_titles) or (
        any(f"grade {n} teacher" in title for n in range(1, 6))
        and ("elementary" in title or "primary" in title or "homeroom" in title)
    )
    if generalist and not subject_blocked and breakdown.sector >= 3 and breakdown.penalties < 10:
        score = max(score, 72)
    job.fit_score = score
    job.fit_category = category_for(score, scoring)
    job.score_breakdown = breakdown
    job.fit_reasons = reasons[:5] or ["Limited direct overlap with the advertised requirements."]
    job.concerns = concerns[:5]
    return job
