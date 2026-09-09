"""Turn RawJobRecord into NormalisedJobRecord. Source fields stay on raw."""

from __future__ import annotations

from job_scout.models.job import NormalisedJobRecord, RawJobRecord
from job_scout.services.geo import geo_from_raw
from job_scout.services.mobility import extract_mobility
from job_scout.services.salary import merge_structured_salary
from job_scout.services.work_mode import classify_from_raw
from job_scout.utils.text import company_key, sha256_text, strip_html


def fingerprint(company: str | None, title: str, city: str | None, country: str | None, work_mode: str) -> str:
    return sha256_text(
        company_key(company),
        company_key(title),
        company_key(city),
        (country or "").upper(),
        work_mode,
    )


def normalise_job(raw: RawJobRecord) -> NormalisedJobRecord:
    description = raw.description_text or strip_html(raw.description_html)
    work_mode = classify_from_raw(raw, description)
    geo = geo_from_raw(raw, description)
    salary = merge_structured_salary(
        text=raw.salary_text,
        min_amount=raw.salary_min,
        max_amount=raw.salary_max,
        currency=raw.salary_currency,
        period=raw.salary_period,
        context=description,
    )
    mobility = extract_mobility(raw.title, description, raw)
    company_norm = company_key(raw.company) or None
    fp = fingerprint(raw.company, raw.title, geo.city, geo.country_code, work_mode.value)
    return NormalisedJobRecord(
        raw=raw,
        title=raw.title.strip(),
        company=raw.company,
        company_normalised=company_norm,
        description=description,
        work_mode=work_mode,
        geo=geo,
        salary=salary,
        mobility=mobility,
        date_posted=raw.date_posted,
        closing_date=raw.closing_date,
        apply_url=raw.apply_url or raw.source_url,
        direct_employer_url=raw.direct_employer_url,
        fingerprint=fp,
    )
