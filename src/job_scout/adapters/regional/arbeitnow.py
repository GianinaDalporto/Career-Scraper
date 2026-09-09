"""Arbeitnow public European job-board API."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class ArbeitnowAdapter(SourceAdapter):
    source_name = "arbeitnow"
    source_type = SourceType.API
    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            payload = client.get_json(self.API_URL, delay=self.config.get("request_delay_seconds", 1.0))
        finally:
            client.close()
        jobs = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            return
        for item in jobs:
            try:
                yield self.parse_job(item)
            except Exception:
                continue

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        remote = bool(payload.get("remote"))
        tags = payload.get("tags") or []
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("slug") or payload.get("url")),
            source_url=payload.get("url") or "",
            title=str(payload.get("title") or ""),
            company=payload.get("company_name") or payload.get("company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=payload.get("location"),
            work_mode_hint="remote" if remote else None,
            date_posted=parse_datetime(payload.get("created_at")),
            apply_url=payload.get("url"),
            raw_payload={"tags": tags},
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
