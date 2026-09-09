"""EURES public job-search JSON. Official EU portal."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

KEYWORDS = (
    "mechanical engineer",
    "project manager engineering",
    "pipeline engineer",
    "water engineer",
)
LOCATIONS = ("de", "nl", "ie", "fr", "es", "pt", "se", "at", "be")


class EuresAdapter(SourceAdapter):
    source_name = "eures"
    source_type = SourceType.API
    SEARCH_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        seen: set[str] = set()
        max_pages = int(self.config.get("max_pages", 2))
        try:
            for keyword in KEYWORDS:
                for country in LOCATIONS[:4]:
                    body = {
                        "resultsPerPage": 20,
                        "page": 1,
                        "sortSearch": "MOST_RECENT",
                        "keywords": [{"keyword": keyword, "specificSearchCode": "EVERYWHERE"}],
                        "locationCodes": [country],
                        "requestLanguage": "en",
                    }
                    for page in range(1, max_pages + 1):
                        body["page"] = page
                        try:
                            payload = client.post_json(
                                self.SEARCH_URL,
                                body,
                                delay=self.config.get("request_delay_seconds", 1.2),
                            )
                        except Exception:
                            break
                        jobs = payload.get("jvs") or payload.get("records") or payload.get("jobs") or []
                        if not jobs:
                            break
                        for item in jobs:
                            jid = str(item.get("id") or item.get("reference") or item.get("jvId"))
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
        title = payload.get("title") or payload.get("jobTitle") or payload.get("originalTitle") or ""
        if isinstance(title, dict):
            title = title.get("en") or next(iter(title.values()), "")
        desc = payload.get("description") or payload.get("jobDescription") or ""
        if isinstance(desc, dict):
            desc = desc.get("en") or next(iter(desc.values()), "")
        location = payload.get("location") or payload.get("city") or payload.get("countryCode")
        salary = payload.get("salary") or payload.get("offeredRemuneration")
        salary_text = str(salary) if salary else None
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("reference") or title),
            source_url=payload.get("url") or payload.get("jvUrl") or "https://europa.eu/eures/",
            title=str(title),
            company=payload.get("employerName") or payload.get("companyName"),
            description_html=str(desc) if desc else None,
            description_text=strip_html(str(desc) if desc else None),
            location_text=str(location) if location else None,
            salary_text=salary_text,
            date_posted=parse_datetime(payload.get("lastModificationDate") or payload.get("creationDate")),
            apply_url=payload.get("applicationUrl") or payload.get("url"),
            raw_payload={"country": payload.get("countryCode")},
            source_preference=SourcePreference.GOVERNMENT,
        )
