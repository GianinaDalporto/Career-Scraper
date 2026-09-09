"""Reusable Workable public widget JSON."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class WorkableAdapter(SourceAdapter):
    source_name = "workable"
    source_type = SourceType.ATS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            for employer in self.config.get("employers") or []:
                if employer.get("enabled") is False or not employer.get("slug"):
                    continue
                slug = employer["slug"]
                url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
                try:
                    payload = client.get_json(
                        url,
                        params={"details": "true"},
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
        location = loc.get("city") or loc.get("country") or ""
        if isinstance(loc, str):
            location = loc
        remote = payload.get("remote") or (isinstance(loc, dict) and loc.get("telecommuting"))
        return RawJobRecord(
            source_name=f"workable:{payload.get('_slug')}",
            source_type=self.source_type,
            source_job_id=str(payload.get("shortcode") or payload.get("id") or payload.get("url")),
            source_url=payload.get("url") or payload.get("application_url") or "",
            title=str(payload.get("title") or ""),
            company=payload.get("_company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=str(location) if location else None,
            work_mode_hint="remote" if remote else None,
            date_posted=parse_datetime(payload.get("published_on") or payload.get("created_at")),
            apply_url=payload.get("application_url") or payload.get("url"),
            direct_employer_url=payload.get("url"),
            raw_payload={"department": payload.get("department")},
            source_preference=SourcePreference.EMPLOYER_ATS,
        )
