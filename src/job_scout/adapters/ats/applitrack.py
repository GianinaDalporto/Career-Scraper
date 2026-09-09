"""Frontline AppliTrack public Output.asp job lists (multi-tenant).

Feed pattern (no auth):
  https://www.applitrack.com/{slug}/onlineapp/jobpostings/Output.asp?all=1

Response is a large HTML/JS document.write payload with escaped quotes.
Only curated tenants with non-empty JobID feeds should be enabled.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import collapse_ws

_JOB_RE = re.compile(
    r"id='wrapword'[^>]*>([^<]{3,300})</td>.*?JobID:\s*(\d+)(.*?)(?=id='wrapword'|</ul>|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_LOCATION_RE = re.compile(
    r"Location:\s*</span>\s*<br/>\s*(?:&nbsp;|\s)*<span[^>]*>([^<]+)</span>",
    re.IGNORECASE,
)
_POSTED_RE = re.compile(
    r"Date Posted:\s*</span>\s*<br/>\s*(?:&nbsp;|\s)*<span[^>]*>([^<]+)</span>",
    re.IGNORECASE,
)
_CLOSING_RE = re.compile(
    r"Closing Date:\s*</span>\s*<br/>\s*(?:&nbsp;|\s)*<span[^>]*>([^<]+)</span>",
    re.IGNORECASE,
)


def _unescape_feed(text: str) -> str:
    # AppliTrack wraps markup in document.write('...'); quotes are backslash-escaped.
    return text.replace("\\'", "'").replace('\\"', '"')


def extract_applitrack_jobs(html: str) -> list[dict[str, Any]]:
    body = _unescape_feed(html)
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _JOB_RE.finditer(body):
        title = collapse_ws(html_lib.unescape(match.group(1)))
        jid = match.group(2)
        block = match.group(3)[:4000]
        if not title or not jid or jid in seen:
            continue
        seen.add(jid)
        loc_m = _LOCATION_RE.search(block)
        posted_m = _POSTED_RE.search(block)
        close_m = _CLOSING_RE.search(block)
        jobs.append(
            {
                "id": jid,
                "title": title,
                "location": collapse_ws(html_lib.unescape(loc_m.group(1))) if loc_m else None,
                "date_posted": collapse_ws(html_lib.unescape(posted_m.group(1))) if posted_m else None,
                "closing": collapse_ws(html_lib.unescape(close_m.group(1))) if close_m else None,
            }
        )
    return jobs


class AppliTrackAdapter(SourceAdapter):
    source_name = "applitrack"
    source_type = SourceType.HTML
    supported_regions = ("US",)

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        # Feeds are often multi-MB; allow a longer timeout than the global default.
        client = HttpClient()
        delay = self.config.get("request_delay_seconds", 1.5)
        timeout = float(self.config.get("request_timeout_seconds") or 90)
        try:
            for tenant in self.config.get("tenants") or []:
                if tenant.get("enabled") is False:
                    continue
                slug = tenant.get("slug")
                if not slug:
                    continue
                company = tenant.get("name") or slug
                location_hint = tenant.get("location_hint")
                url = (
                    f"https://www.applitrack.com/{slug}/onlineapp/"
                    f"jobpostings/Output.asp?all=1"
                )
                try:
                    html = client.get_text(url, delay=delay, timeout=timeout)
                except Exception:
                    continue
                for item in extract_applitrack_jobs(html):
                    item["_company"] = company
                    item["_slug"] = slug
                    item["_location_hint"] = location_hint
                    try:
                        yield self.parse_job(item)
                    except Exception:
                        continue
        finally:
            client.close()

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        slug = str(payload.get("_slug") or "")
        jid = str(payload.get("id") or "")
        apply = (
            f"https://www.applitrack.com/{slug}/onlineapp/jobpostings/"
            f"view.asp?AppliTrackJobId={jid}"
        )
        location = payload.get("location") or payload.get("_location_hint")
        posted_raw = payload.get("date_posted")
        date_posted = parse_datetime(posted_raw) if posted_raw else None
        if date_posted is None and isinstance(posted_raw, str) and posted_raw:
            # AppliTrack often uses M/D/YYYY
            for fmt in ("%m/%d/%Y", "%m/%d/%y"):
                try:
                    date_posted = datetime.strptime(posted_raw.strip(), fmt)
                    break
                except ValueError:
                    continue

        closing = payload.get("closing")
        closing_date = None
        if isinstance(closing, str) and closing and "until filled" not in closing.lower():
            parsed = parse_datetime(closing)
            if parsed:
                closing_date = parsed.date()

        return RawJobRecord(
            source_name=f"applitrack:{slug}",
            source_type=self.source_type,
            source_job_id=jid,
            source_url=apply,
            title=str(payload.get("title") or ""),
            company=payload.get("_company"),
            location_text=str(location) if location else None,
            work_mode_hint="onsite",
            date_posted=date_posted,
            closing_date=closing_date,
            apply_url=apply,
            direct_employer_url=apply,
            raw_payload={"closing_text": closing},
            source_preference=SourcePreference.EMPLOYER_CAREER,
        )
