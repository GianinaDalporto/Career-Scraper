"""Eightfold public apply API — multi-tenant district career boards.

Example (Houston ISD):
GET https://apply.houstonisd.org/api/apply/v2/jobs?domain=houstonisd.org&num=50&start=0&query=teacher
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.text import strip_html

DEFAULT_QUERIES = (
    "elementary teacher",
    "grade 1 teacher",
    "grade 2 teacher",
    "grade 3 teacher",
    "administrative assistant",
)


class EightfoldAdapter(SourceAdapter):
    source_name = "eightfold"
    source_type = SourceType.ATS
    supported_regions = ("US",)

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        page_size = int(self.config.get("page_size") or 50)
        max_pages = int(self.config.get("max_pages") or 4)
        delay = self.config.get("request_delay_seconds", 1.0)
        seen: set[str] = set()
        try:
            for tenant in self.config.get("tenants") or []:
                if tenant.get("enabled") is False:
                    continue
                base = (tenant.get("base_url") or "").rstrip("/")
                domain = tenant.get("domain")
                if not base or not domain:
                    continue
                company = tenant.get("name") or domain
                queries = tenant.get("queries") or self.config.get("queries") or list(DEFAULT_QUERIES)
                url = f"{base}/api/apply/v2/jobs"
                for query in queries:
                    for page in range(max_pages):
                        start = page * page_size
                        try:
                            payload = client.get_json(
                                url,
                                params={
                                    "domain": domain,
                                    "num": page_size,
                                    "start": start,
                                    "query": query,
                                },
                                delay=delay,
                            )
                        except Exception:
                            break
                        positions = payload.get("positions") if isinstance(payload, dict) else None
                        if not isinstance(positions, list) or not positions:
                            break
                        for item in positions:
                            if not isinstance(item, dict):
                                continue
                            jid = str(item.get("id") or item.get("ats_job_id") or "")
                            if not jid or jid in seen:
                                continue
                            seen.add(jid)
                            item = {
                                **item,
                                "_company": company,
                                "_tenant": tenant.get("slug") or domain,
                                "_base_url": base,
                            }
                            try:
                                yield self.parse_job(item)
                            except Exception:
                                continue
                        if len(positions) < page_size:
                            break
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        jid = str(payload.get("id") or payload.get("ats_job_id") or "")
        apply = (
            payload.get("canonicalPositionUrl")
            or f"{payload.get('_base_url')}/careers/job/{jid}"
        )
        work_opt = str(payload.get("work_location_option") or "").lower()
        work_hint = None
        if work_opt in {"onsite", "hybrid", "remote"}:
            work_hint = work_opt
        elif "remote" in work_opt:
            work_hint = "remote"
        elif "hybrid" in work_opt:
            work_hint = "hybrid"
        elif work_opt:
            work_hint = "onsite"

        created = payload.get("t_create")
        date_posted = None
        if isinstance(created, (int, float)) and created > 0:
            # Eightfold sometimes uses ms; normalise to seconds.
            ts = float(created)
            if ts > 1e12:
                ts /= 1000.0
            date_posted = datetime.fromtimestamp(ts, tz=timezone.utc)

        desc_html = payload.get("job_description") or None
        location = payload.get("location")
        if not location and isinstance(payload.get("locations"), list) and payload["locations"]:
            location = payload["locations"][0]

        return RawJobRecord(
            source_name=f"eightfold:{payload.get('_tenant')}",
            source_type=self.source_type,
            source_job_id=jid,
            source_url=str(apply),
            title=str(payload.get("name") or payload.get("posting_name") or ""),
            company=payload.get("_company"),
            description_html=desc_html,
            description_text=strip_html(desc_html) if desc_html else None,
            location_text=str(location) if location else None,
            work_mode_hint=work_hint,
            date_posted=date_posted,
            apply_url=str(apply),
            direct_employer_url=str(apply),
            raw_payload={
                "department": payload.get("department"),
                "display_job_id": payload.get("display_job_id"),
                "work_location_option": payload.get("work_location_option"),
            },
            source_preference=SourcePreference.EMPLOYER_ATS,
        )
