"""Remotive public API — https://remotive.com/api/remote-jobs"""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

SEARCHES = (
    "mechanical engineer",
    "project manager",
    "engineering manager",
    "operations manager",
    "automation",
    "technical product manager",
)


class RemotiveAdapter(SourceAdapter):
    source_name = "remotive"
    source_type = SourceType.API
    API_URL = "https://remotive.com/api/remote-jobs"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        seen: set[str] = set()
        try:
            for query in SEARCHES:
                payload = client.get_json(
                    self.API_URL,
                    params={"search": query, "limit": 50},
                    delay=self.config.get("request_delay_seconds", 1.0),
                )
                jobs = payload.get("jobs") if isinstance(payload, dict) else payload
                if not isinstance(jobs, list):
                    continue
                for item in jobs:
                    if not isinstance(item, dict):
                        continue
                    jid = str(item.get("id") or item.get("url"))
                    if jid in seen:
                        continue
                    seen.add(jid)
                    try:
                        yield self.parse_job(item)
                    except Exception:
                        continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("url")),
            source_url=payload.get("url") or payload.get("job_url") or "",
            title=str(payload.get("title") or ""),
            company=payload.get("company_name") or payload.get("company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=payload.get("candidate_required_location") or payload.get("location") or "Worldwide",
            work_mode_hint="remote",
            salary_text=payload.get("salary"),
            date_posted=parse_datetime(payload.get("publication_date")),
            apply_url=payload.get("url"),
            raw_payload={"category": payload.get("category"), "job_type": payload.get("job_type")},
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
