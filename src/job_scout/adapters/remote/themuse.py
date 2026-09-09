"""The Muse public jobs API — https://www.themuse.com/api/public/jobs

Used for US admin-assistant / education-category inventory. No auth.
Category feeds are noisy; title filters keep the stream usable for Nina.
"""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

DEFAULT_TITLE_KEYWORDS = (
    "administrative assistant",
    "admin assistant",
    "office assistant",
    "school secretary",
    "executive assistant",
    "reception",
)


class TheMuseAdapter(SourceAdapter):
    source_name = "themuse"
    source_type = SourceType.API
    supported_regions = ("US", "global")
    API_URL = "https://www.themuse.com/api/public/jobs"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient(allowed_hosts={"www.themuse.com"})
        max_pages = int(self.config.get("max_pages") or 8)
        category = self.config.get("category") or "Education"
        keywords = [
            k.lower()
            for k in (self.config.get("title_keywords") or list(DEFAULT_TITLE_KEYWORDS))
        ]
        location_hints = [
            h.lower() for h in (self.config.get("location_hints") or []) if h
        ]
        delay = self.config.get("request_delay_seconds", 1.0)
        seen: set[str] = set()
        try:
            for page in range(1, max_pages + 1):
                try:
                    payload = client.get_json(
                        self.API_URL,
                        params={"category": category, "page": page},
                        delay=delay,
                    )
                except Exception:
                    break
                results = payload.get("results") if isinstance(payload, dict) else None
                if not isinstance(results, list) or not results:
                    break
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("name") or "").lower()
                    if keywords and not any(k in title for k in keywords):
                        continue
                    if location_hints:
                        locs = " ".join(
                            str(loc.get("name") or "")
                            for loc in (item.get("locations") or [])
                            if isinstance(loc, dict)
                        ).lower()
                        if locs and not any(h in locs for h in location_hints):
                            continue
                    jid = str(item.get("id") or item.get("short_name") or "")
                    if not jid or jid in seen:
                        continue
                    seen.add(jid)
                    try:
                        yield self.parse_job(item)
                    except Exception:
                        continue
                page_count = int(payload.get("page_count") or 0)
                if page_count and page >= page_count:
                    break
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        company = payload.get("company") or {}
        company_name = company.get("name") if isinstance(company, dict) else None
        refs = payload.get("refs") or {}
        landing = refs.get("landing_page") if isinstance(refs, dict) else None
        locations = [
            str(loc.get("name"))
            for loc in (payload.get("locations") or [])
            if isinstance(loc, dict) and loc.get("name")
        ]
        contents = payload.get("contents")
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("short_name")),
            source_url=str(landing or ""),
            title=str(payload.get("name") or ""),
            company=company_name,
            description_html=contents,
            description_text=strip_html(contents),
            location_text=", ".join(locations) if locations else None,
            date_posted=parse_datetime(payload.get("publication_date")),
            apply_url=str(landing) if landing else None,
            raw_payload={
                "categories": [
                    c.get("name")
                    for c in (payload.get("categories") or [])
                    if isinstance(c, dict)
                ],
                "levels": [
                    lv.get("name")
                    for lv in (payload.get("levels") or [])
                    if isinstance(lv, dict)
                ],
            },
            source_preference=SourcePreference.AGGREGATOR,
        )
