"""We Work Remotely official RSS feeds."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

FEEDS = (
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-product-jobs.rss",
    "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
)


class WeWorkRemotelyAdapter(SourceAdapter):
    source_name = "weworkremotely"
    source_type = SourceType.RSS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        seen: set[str] = set()
        try:
            for url in FEEDS:
                entries = client.get_rss(url, delay=self.config.get("request_delay_seconds", 1.0))
                for entry in entries:
                    key = str(entry.get("id") or entry.get("link"))
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        yield self.parse_job(entry)
                    except Exception:
                        continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        title = str(payload.get("title") or "")
        company = None
        if ":" in title:
            company, _, rest = title.partition(":")
            title = rest.strip() or title
            company = company.strip()
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("link")),
            source_url=str(payload.get("link") or ""),
            title=title,
            company=company,
            description_html=payload.get("summary") or payload.get("description"),
            description_text=strip_html(payload.get("summary") or payload.get("description")),
            location_text="Remote",
            work_mode_hint="remote",
            date_posted=parse_datetime(payload.get("published") or payload.get("updated")),
            apply_url=payload.get("link"),
            raw_payload={"feed": True},
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
