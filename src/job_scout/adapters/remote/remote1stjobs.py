"""Remote1stJobs public JSON dump — remote-first EMEA/global board."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

API_URL = "https://www.remote1stjobs.com/jobs.json"


class Remote1stJobsAdapter(SourceAdapter):
    source_name = "remote1stjobs"
    source_type = SourceType.API

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            payload = client.get_json(
                API_URL,
                delay=self.config.get("request_delay_seconds", 1.0),
            )
        finally:
            client.close()
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            return
        limit = int(self.config.get("max_jobs_per_source", 250))
        for item in jobs[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                yield self.parse_job(item)
            except Exception:
                continue

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        location = str(payload.get("location") or "Remote")
        location_l = location.lower()
        if "hybrid" in location_l:
            remote_hint = "hybrid"
        elif "remote" in location_l or location_l.strip() in {"", "worldwide", "global", "anywhere"}:
            remote_hint = "remote"
        else:
            remote_hint = None
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("remote1stjobs entry missing url")
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=url,
            source_url=url,
            title=str(payload.get("title") or ""),
            company=payload.get("company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=location,
            work_mode_hint=remote_hint,
            date_posted=parse_datetime(payload.get("created_at") or payload.get("published_at")),
            apply_url=url,
            raw_payload={
                "category": payload.get("category"),
                "job_type": payload.get("job_type"),
            },
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
