"""USAJOBS official Search API. Disabled until USAJOBS_API_KEY is set."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.config.settings import get_settings
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_date, parse_datetime
from job_scout.utils.text import strip_html


class UsaJobsAdapter(SourceAdapter):
    source_name = "usajobs"
    source_type = SourceType.API
    API_URL = "https://data.usajobs.gov/api/search"

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        settings = get_settings()
        if not settings.usajobs_api_key:
            return
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": settings.usajobs_user_agent or settings.job_scout_user_agent,
            "Authorization-Key": settings.usajobs_api_key,
        }
        client = HttpClient(
            allowed_hosts={"data.usajobs.gov"},
            follow_redirects=False,
        )
        try:
            for keyword in ("Mechanical Engineer", "Project Manager", "Pipeline"):
                payload = client.get_json(
                    self.API_URL,
                    params={"Keyword": keyword, "ResultsPerPage": 50},
                    headers=headers,
                    delay=self.config.get("request_delay_seconds", 1.0),
                )
                items = (((payload.get("SearchResult") or {}).get("SearchResultItems")) or [])
                for wrapper in items:
                    item = wrapper.get("MatchedObjectDescriptor") or wrapper
                    try:
                        yield self.parse_job(item)
                    except Exception:
                        continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        remun = payload.get("PositionRemuneration") or []
        salary_min = salary_max = currency = period = None
        salary_text = None
        if remun:
            first = remun[0]
            salary_min = first.get("MinimumRange")
            salary_max = first.get("MaximumRange")
            period = first.get("RateIntervalCode")
            salary_text = f"{salary_min}-{salary_max} {period}"
            currency = "USD"
        loc = payload.get("PositionLocationDisplay") or ""
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("PositionID") or payload.get("PositionURI")),
            source_url=payload.get("PositionURI") or "",
            title=str(payload.get("PositionTitle") or ""),
            company=payload.get("OrganizationName"),
            description_html=payload.get("UserArea", {}).get("Details", {}).get("JobSummary")
            if isinstance(payload.get("UserArea"), dict)
            else payload.get("QualificationSummary"),
            description_text=strip_html(payload.get("QualificationSummary")),
            location_text=loc,
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period="annual" if period in {"PA", "Per Year"} else period,
            date_posted=parse_datetime(payload.get("PublicationStartDate")),
            closing_date=parse_date(payload.get("ApplicationCloseDate")),
            apply_url=payload.get("ApplyURI", [None])[0] if isinstance(payload.get("ApplyURI"), list) else payload.get("PositionURI"),
            direct_employer_url=payload.get("PositionURI"),
            raw_payload={"who_may_apply": payload.get("JobGrade")},
            source_preference=SourcePreference.GOVERNMENT,
        )
