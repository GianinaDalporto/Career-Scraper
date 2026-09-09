"""RemoteOK public API — https://remoteok.com/api"""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class RemoteOKAdapter(SourceAdapter):
    source_name = "remoteok"
    source_type = SourceType.API
    API_URL = "https://remoteok.com/api"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            payload = client.get_json(self.API_URL, delay=self.config.get("request_delay_seconds", 1.0))
        finally:
            client.close()
        if not isinstance(payload, list):
            return
        for item in payload:
            if not isinstance(item, dict) or not item.get("id") or not item.get("position"):
                continue
            try:
                yield self.parse_job(item)
            except Exception:
                continue

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        salary_text = payload.get("salary") or payload.get("salary_min") and (
            f"{payload.get('salary_min')}-{payload.get('salary_max')} {payload.get('salary_currency') or 'USD'}"
        )
        location = payload.get("location") or "Worldwide"
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("slug") or payload.get("url")),
            source_url=payload.get("url") or payload.get("apply_url") or f"https://remoteok.com/remote-jobs/{payload.get('id')}",
            title=str(payload.get("position") or payload.get("title")),
            company=payload.get("company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=str(location),
            work_mode_hint="remote",
            salary_text=str(salary_text) if salary_text else None,
            salary_min=payload.get("salary_min"),
            salary_max=payload.get("salary_max"),
            salary_currency=payload.get("salary_currency") or "USD",
            salary_period="annual",
            date_posted=parse_datetime(payload.get("date") or payload.get("epoch")),
            apply_url=payload.get("apply_url") or payload.get("url"),
            raw_payload={"keys": sorted(str(k) for k in payload.keys())},
            source_preference=SourcePreference.AGGREGATOR,
        )
