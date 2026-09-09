"""Reusable Ashby job-board API."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class AshbyAdapter(SourceAdapter):
    source_name = "ashby"
    source_type = SourceType.ATS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            for employer in self.config.get("employers") or []:
                if employer.get("enabled") is False or not employer.get("slug"):
                    continue
                slug = employer["slug"]
                url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                try:
                    payload = client.get_json(
                        url,
                        params={"includeCompensation": "true"},
                        delay=self.config.get("request_delay_seconds", 1.0),
                    )
                except Exception:
                    continue
                for item in payload.get("jobs") or []:
                    item["_company"] = employer.get("name") or slug
                    item["_slug"] = slug
                    try:
                        yield self.parse_job(item)
                    except Exception:
                        continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        loc = payload.get("location") or {}
        location = loc.get("locationSummary") if isinstance(loc, dict) else str(loc or "")
        remote = False
        if isinstance(loc, dict):
            remote = bool(loc.get("isRemote"))
        comp = payload.get("compensation") or {}
        salary_min = salary_max = currency = period = None
        salary_text = None
        if isinstance(comp, dict) and comp:
            salary_min = (comp.get("compensationTierSummary") or {})
            currency = comp.get("currencyCode")
            period = (comp.get("interval") or "YEAR").lower()
            if "YEAR" in str(comp.get("interval") or "").upper():
                period = "annual"
            components = comp.get("summaryComponents") or comp.get("compensationTiers") or []
            if components and isinstance(components, list):
                first = components[0] if isinstance(components[0], dict) else {}
                salary_min = first.get("minValue") or first.get("min")
                salary_max = first.get("maxValue") or first.get("max")
            salary_text = str(comp)
        return RawJobRecord(
            source_name=f"ashby:{payload.get('_slug')}",
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("jobUrl")),
            source_url=payload.get("jobUrl") or payload.get("applyUrl") or "",
            title=str(payload.get("title") or ""),
            company=payload.get("_company"),
            description_html=payload.get("descriptionHtml") or payload.get("descriptionPlain"),
            description_text=strip_html(payload.get("descriptionHtml") or payload.get("descriptionPlain")),
            location_text=location or None,
            work_mode_hint="remote" if remote else None,
            salary_text=salary_text if isinstance(salary_text, str) else None,
            salary_min=salary_min if not isinstance(salary_min, dict) else None,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period=period,
            date_posted=parse_datetime(payload.get("publishedAt") or payload.get("updatedAt")),
            apply_url=payload.get("applyUrl") or payload.get("jobUrl"),
            direct_employer_url=payload.get("jobUrl"),
            raw_payload={"department": payload.get("department")},
            source_preference=SourcePreference.EMPLOYER_ATS,
        )
