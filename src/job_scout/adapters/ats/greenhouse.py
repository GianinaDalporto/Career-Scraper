"""Reusable Greenhouse boards API. Employers come from configuration."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class GreenhouseAdapter(SourceAdapter):
    source_name = "greenhouse"
    source_type = SourceType.ATS
    supported_regions = ("global", "ZA", "US", "EU", "AU")

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            for employer in self.config.get("employers") or []:
                if employer.get("enabled") is False:
                    continue
                slug = employer.get("slug")
                if not slug:
                    continue
                url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                try:
                    payload = client.get_json(
                        url,
                        params={"content": "true"},
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
        location = ""
        if isinstance(payload.get("location"), dict):
            location = payload["location"].get("name") or ""
        offices = payload.get("offices") or []
        if not location and offices:
            location = offices[0].get("name") or ""
        metadata = payload.get("metadata") or []
        salary_text = None
        for item in metadata:
            name = str(item.get("name") or "").lower()
            if "salary" in name or "compensation" in name:
                salary_text = str(item.get("value") or "")
        return RawJobRecord(
            source_name=f"greenhouse:{payload.get('_slug')}",
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("internal_job_id")),
            source_url=payload.get("absolute_url") or "",
            title=str(payload.get("title") or ""),
            company=payload.get("_company"),
            description_html=payload.get("content"),
            description_text=strip_html(payload.get("content")),
            location_text=location or None,
            salary_text=salary_text,
            date_posted=parse_datetime(payload.get("updated_at") or payload.get("created_at")),
            apply_url=payload.get("absolute_url"),
            direct_employer_url=payload.get("absolute_url"),
            raw_payload={"department": (payload.get("departments") or [{}])[0].get("name") if payload.get("departments") else None},
            source_preference=SourcePreference.EMPLOYER_ATS,
        )
