"""Himalayas public API — location + timezone restrictions included."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

SEARCHES = ("mechanical", "project manager", "engineering manager", "operations", "automation")


class HimalayasAdapter(SourceAdapter):
    source_name = "himalayas"
    source_type = SourceType.API
    SEARCH_URL = "https://himalayas.app/jobs/api/search"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        seen: set[str] = set()
        max_pages = int(self.config.get("max_pages", 3))
        try:
            for query in SEARCHES:
                for page in range(1, max_pages + 1):
                    payload = client.get_json(
                        self.SEARCH_URL,
                        params={"q": query, "page": page, "sort": "recent"},
                        delay=self.config.get("request_delay_seconds", 1.2),
                    )
                    jobs = payload.get("jobs") if isinstance(payload, dict) else []
                    if not jobs:
                        break
                    for item in jobs:
                        guid = str(item.get("guid") or item.get("applicationLink"))
                        if guid in seen:
                            continue
                        seen.add(guid)
                        try:
                            yield self.parse_job(item)
                        except Exception:
                            continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        restrictions = payload.get("locationRestrictions") or []
        countries = []
        for item in restrictions:
            if isinstance(item, dict) and item.get("alpha2"):
                countries.append(str(item["alpha2"]).upper())
            elif isinstance(item, str):
                countries.append(item.upper())
        tzs = [str(t) for t in (payload.get("timezoneRestrictions") or [])]
        expiry = parse_datetime(payload.get("expiryDate"))
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("guid") or payload.get("applicationLink")),
            source_url=payload.get("applicationLink") or "",
            title=str(payload.get("title") or ""),
            company=payload.get("companyName"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description") or payload.get("excerpt")),
            location_text="Worldwide" if not countries else ", ".join(countries),
            work_mode_hint="remote",
            salary_min=payload.get("minSalary"),
            salary_max=payload.get("maxSalary"),
            salary_currency=payload.get("currency"),
            salary_period=payload.get("salaryPeriod") or "annual",
            date_posted=parse_datetime(payload.get("pubDate")),
            closing_date=expiry.date() if expiry else None,
            apply_url=payload.get("applicationLink"),
            remote_countries=countries,
            timezone_restrictions=tzs,
            raw_payload={"categories": payload.get("categories") or []},
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
