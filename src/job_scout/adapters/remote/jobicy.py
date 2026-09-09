"""Jobicy public API — https://jobicy.com/api/v2/remote-jobs"""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class JobicyAdapter(SourceAdapter):
    source_name = "jobicy"
    source_type = SourceType.API
    API_URL = "https://jobicy.com/api/v2/remote-jobs"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            payload = client.get_json(
                self.API_URL,
                params={"count": 100},
                delay=self.config.get("request_delay_seconds", 1.0),
            )
        finally:
            client.close()
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            return
        for item in jobs:
            if not isinstance(item, dict):
                continue
            try:
                yield self.parse_job(item)
            except Exception:
                continue

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        salary_text = payload.get("salary") or payload.get("jobSalary")
        geo = payload.get("jobGeo") or payload.get("geo") or "Worldwide"
        countries = []
        if isinstance(geo, str) and geo.lower() not in {"anywhere", "worldwide", "global"}:
            countries = [geo]
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("jobId") or payload.get("url")),
            source_url=payload.get("url") or payload.get("jobUrl") or "",
            title=str(payload.get("jobTitle") or payload.get("title") or ""),
            company=payload.get("companyName") or payload.get("company"),
            description_html=payload.get("jobDescription") or payload.get("description"),
            description_text=strip_html(payload.get("jobDescription") or payload.get("description")),
            location_text=str(geo),
            work_mode_hint="remote",
            salary_text=str(salary_text) if salary_text else None,
            date_posted=parse_datetime(payload.get("pubDate") or payload.get("jobPubDate")),
            apply_url=payload.get("url") or payload.get("applicationUrl"),
            remote_countries=countries if isinstance(countries, list) else [],
            raw_payload={"industry": payload.get("jobIndustry") or payload.get("industry")},
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
