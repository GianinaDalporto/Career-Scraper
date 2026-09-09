"""Adzuna official developer API. Disabled until APP_ID/APP_KEY are set."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.config.settings import get_settings
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

COUNTRIES = ("za", "us", "au", "de", "nl")
QUERIES = ("mechanical engineer", "project manager", "pipeline engineer")

_COUNTRY_CURRENCY = {
    "za": "ZAR",
    "us": "USD",
    "au": "AUD",
    "de": "EUR",
    "nl": "EUR",
}


def _currency_for_country(country: str | None) -> str:
    return _COUNTRY_CURRENCY.get((country or "").lower(), "USD")


class AdzunaAdapter(SourceAdapter):
    source_name = "adzuna"
    source_type = SourceType.API

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        settings = get_settings()
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            return
        client = HttpClient()
        try:
            for country in COUNTRIES:
                for what in QUERIES:
                    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                    try:
                        payload = client.get_json(
                            url,
                            params={
                                "app_id": settings.adzuna_app_id,
                                "app_key": settings.adzuna_app_key,
                                "what": what,
                                "results_per_page": 20,
                                "content-type": "application/json",
                            },
                            delay=self.config.get("request_delay_seconds", 1.0),
                        )
                    except Exception:
                        continue
                    for item in payload.get("results") or []:
                        item["_country"] = country
                        try:
                            yield self.parse_job(item)
                        except Exception:
                            continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        loc = payload.get("location") or {}
        location = ", ".join(loc.get("area") or []) if isinstance(loc, dict) else str(loc)
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("redirect_url")),
            source_url=payload.get("redirect_url") or "",
            title=str(payload.get("title") or ""),
            company=(payload.get("company") or {}).get("display_name") if isinstance(payload.get("company"), dict) else payload.get("company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=location or None,
            salary_min=payload.get("salary_min"),
            salary_max=payload.get("salary_max"),
            salary_currency=_currency_for_country(payload.get("_country")),
            salary_period="annual",
            date_posted=parse_datetime(payload.get("created")),
            apply_url=payload.get("redirect_url"),
            raw_payload={"country": payload.get("_country")},
            source_preference=SourcePreference.AGGREGATOR,
        )
