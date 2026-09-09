"""ReliefWeb jobs RSS — humanitarian / WASH / infrastructure postings."""

from __future__ import annotations

import re
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html

FEED_URL = "https://reliefweb.int/jobs/rss.xml"
_COUNTRY_RE = re.compile(r"Country:\s*([^<\n]+)", re.IGNORECASE)


class ReliefWebAdapter(SourceAdapter):
    source_name = "reliefweb"
    source_type = SourceType.RSS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient()
        try:
            entries = client.get_rss(
                FEED_URL,
                delay=self.config.get("request_delay_seconds", 1.0),
            )
            for entry in entries:
                try:
                    yield self.parse_job(entry)
                except Exception:
                    continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        summary = str(payload.get("summary") or payload.get("description") or "")
        text = strip_html(summary)
        country = None
        match = _COUNTRY_RE.search(summary) or _COUNTRY_RE.search(text)
        if match:
            country = match.group(1).strip()
        tags = payload.get("tags") or []
        if not country and isinstance(tags, list) and tags:
            term = tags[0].get("term") if isinstance(tags[0], dict) else None
            if term:
                country = str(term)
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("link")),
            source_url=str(payload.get("link") or ""),
            title=str(payload.get("title") or ""),
            company=payload.get("author") or "ReliefWeb listing",
            description_html=summary or None,
            description_text=text or None,
            location_text=country,
            work_mode_hint=None,
            date_posted=parse_datetime(payload.get("published") or payload.get("updated")),
            apply_url=payload.get("link"),
            raw_payload={"feed": FEED_URL},
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
