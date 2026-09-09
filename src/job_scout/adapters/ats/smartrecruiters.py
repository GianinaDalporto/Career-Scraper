"""Reusable SmartRecruiters public postings API."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

logger = logging.getLogger(__name__)


def _public_job_url(payload: dict[str, Any], slug: str) -> str:
    """Prefer human-facing board URLs; never use the API `ref` as the apply link."""
    for key in ("postingUrl", "applyUrl", "publicUrl"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("http") and "api.smartrecruiters.com" not in value:
            return value
    job_id = payload.get("id") or payload.get("uuid")
    if slug and job_id:
        return f"https://jobs.smartrecruiters.com/{slug}/{job_id}"
    return ""


class SmartRecruitersAdapter(SourceAdapter):
    source_name = "smartrecruiters"
    source_type = SourceType.ATS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient(allowed_hosts={"api.smartrecruiters.com", "jobs.smartrecruiters.com"})
        max_pages = int(self.config.get("max_pages", 3))
        max_jobs = int(self.config.get("max_jobs_per_source", 250))
        max_per_employer = int(self.config.get("max_jobs_per_employer", max_jobs))
        yielded = 0
        try:
            for employer in self.config.get("employers") or []:
                if employer.get("enabled") is False or not employer.get("slug"):
                    continue
                if yielded >= max_jobs:
                    break
                slug = employer["slug"]
                employer_yielded = 0
                offset = 0
                for _ in range(max_pages):
                    if yielded >= max_jobs or employer_yielded >= max_per_employer:
                        break
                    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
                    try:
                        payload = client.get_json(
                            url,
                            params={"limit": 100, "offset": offset},
                            delay=self.config.get("request_delay_seconds", 1.0),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("SmartRecruiters list failed for slug=%s: %s", slug, type(exc).__name__)
                        break
                    jobs = payload.get("content") or payload.get("jobs") or []
                    if not jobs:
                        break
                    for item in jobs:
                        if yielded >= max_jobs or employer_yielded >= max_per_employer:
                            break
                        detail = item
                        job_id = item.get("id") or item.get("uuid")
                        if job_id and not (item.get("jobAd") or item.get("description")):
                            detail_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{job_id}"
                            try:
                                detail = client.get_json(
                                    detail_url,
                                    delay=self.config.get("request_delay_seconds", 1.0),
                                )
                                if isinstance(detail, dict):
                                    detail = {**item, **detail}
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(
                                    "SmartRecruiters detail failed slug=%s id=%s: %s",
                                    slug,
                                    job_id,
                                    type(exc).__name__,
                                )
                                detail = item
                        detail["_company"] = employer.get("name") or slug
                        detail["_slug"] = slug
                        try:
                            yield self.parse_job(detail)
                            yielded += 1
                            employer_yielded += 1
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("SmartRecruiters parse failed slug=%s: %s", slug, type(exc).__name__)
                            continue
                    offset += 100
                    if len(jobs) < 100:
                        break
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        loc = payload.get("location") or {}
        city = loc.get("city")
        country = loc.get("countryCode") or loc.get("country")
        location = ", ".join(p for p in [city, country] if p)
        remote = loc.get("remote") or payload.get("remote")
        slug = str(payload.get("_slug") or "")
        public_url = _public_job_url(payload, slug)
        job_ad = payload.get("jobAd") if isinstance(payload.get("jobAd"), dict) else {}
        sections = job_ad.get("sections") if isinstance(job_ad, dict) else {}
        desc_html = None
        if isinstance(sections, dict):
            desc_html = (sections.get("jobDescription") or {}).get("text")
        if not desc_html:
            desc_html = payload.get("description")
        return RawJobRecord(
            source_name=f"smartrecruiters:{slug}",
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("uuid") or payload.get("refNumber")),
            source_url=public_url,
            title=str(payload.get("name") or payload.get("title") or ""),
            company=payload.get("_company"),
            description_html=desc_html,
            description_text=strip_html(desc_html),
            location_text=location or None,
            work_mode_hint="remote" if remote else None,
            date_posted=parse_datetime(payload.get("releasedDate") or payload.get("createdOn")),
            apply_url=public_url,
            direct_employer_url=public_url,
            raw_payload={
                "department": (payload.get("department") or {}).get("label")
                if isinstance(payload.get("department"), dict)
                else payload.get("department"),
                "api_ref": payload.get("ref"),
            },
            source_preference=SourcePreference.EMPLOYER_ATS,
        )
