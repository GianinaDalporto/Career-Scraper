"""Reusable Lever postings API."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class LeverAdapter(SourceAdapter):
    source_name = "lever"
    source_type = SourceType.ATS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            for employer in self.config.get("employers") or []:
                if employer.get("enabled") is False:
                    continue
                slug = employer.get("slug")
                if not slug:
                    continue
                url = f"https://api.lever.co/v0/postings/{slug}"
                try:
                    payload = client.get_json(
                        url,
                        params={"mode": "json"},
                        delay=self.config.get("request_delay_seconds", 1.0),
                    )
                except Exception:
                    continue
                jobs = payload if isinstance(payload, list) else payload.get("data") or []
                for item in jobs:
                    item["_company"] = employer.get("name") or slug
                    item["_slug"] = slug
                    try:
                        yield self.parse_job(item)
                    except Exception:
                        continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        cats = payload.get("categories") or {}
        location = cats.get("location") or payload.get("country")
        work_mode = None
        if str(cats.get("commitment") or "").lower().find("remote") >= 0:
            work_mode = "remote"
        salary_text = None
        salary_min = None
        salary_max = None
        salary_currency = None
        salary_period = None
        salary = payload.get("salaryRange") or payload.get("salary")
        if isinstance(salary, dict):
            raw_min = salary.get("min")
            raw_max = salary.get("max")
            try:
                salary_min = Decimal(str(raw_min)) if raw_min is not None else None
            except Exception:
                salary_min = None
            try:
                salary_max = Decimal(str(raw_max)) if raw_max is not None else None
            except Exception:
                salary_max = None
            salary_currency = salary.get("currency")
            interval = str(salary.get("interval") or salary.get("period") or "").lower()
            if interval in {"per-year-salary", "yearly", "year", "annual"}:
                salary_period = "annual"
            elif interval in {"per-month-salary", "monthly", "month"}:
                salary_period = "monthly"
            elif interval in {"per-hour-salary", "hourly", "hour"}:
                salary_period = "hourly"
            parts = []
            if salary_min is not None:
                parts.append(str(salary_min))
            if salary_max is not None and salary_max != salary_min:
                parts.append(str(salary_max))
            if parts:
                salary_text = "-".join(parts)
                if salary_currency:
                    salary_text = f"{salary_text} {salary_currency}"
                if salary_period:
                    salary_text = f"{salary_text} {salary_period}"
        return RawJobRecord(
            source_name=f"lever:{payload.get('_slug')}",
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("hostedUrl")),
            source_url=payload.get("hostedUrl") or payload.get("applyUrl") or "",
            title=str(payload.get("text") or payload.get("title") or ""),
            company=payload.get("_company"),
            description_html=payload.get("descriptionPlain") or payload.get("description"),
            description_text=strip_html(payload.get("descriptionPlain") or payload.get("description")),
            location_text=location,
            work_mode_hint=work_mode,
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_period=salary_period,
            date_posted=parse_datetime(payload.get("createdAt")),
            apply_url=payload.get("applyUrl") or payload.get("hostedUrl"),
            direct_employer_url=payload.get("hostedUrl"),
            raw_payload={"team": cats.get("team")},
            source_preference=SourcePreference.EMPLOYER_ATS,
        )
