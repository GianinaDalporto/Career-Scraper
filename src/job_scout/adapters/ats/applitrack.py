"""Frontline AppliTrack public Output.asp job lists (multi-tenant).

Feed pattern (no auth):
  https://www.applitrack.com/{slug}/onlineapp/jobpostings/Output.asp?all=1

Detail (optional, bounded):
  .../Output.asp?AppliTrackJobId={id}&AppliTrackLayoutMode=detail&AppliTrackViewPosting=1

Response is a large HTML/JS document.write payload with escaped quotes.
Only curated tenants with non-empty JobID feeds should be enabled.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from datetime import datetime
from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import collapse_ws, strip_html

logger = logging.getLogger(__name__)

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

# Detail pages embed Position Purpose / Qualifications blocks.
_DETAIL_SECTION_RE = re.compile(
    r"(Position Purpose|Qualifications|Major Responsibilities|Essential Functions|"
    r"Job Description|Duties|Role Overview)</(?:strong|span|b)>",
    re.IGNORECASE,
)

_DETAIL_TITLE_HINTS = (
    "teacher",
    "tutor",
    "instructor",
    "educator",
    "principal",
    "assistant",
    "secretary",
    "clerk",
    "paraprofessional",
    "aide",
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


def extract_applitrack_detail_text(html: str) -> str | None:
    """Best-effort plain text from an AppliTrack detail Output.asp page."""
    body = _unescape_feed(html)
    if not _DETAIL_SECTION_RE.search(body):
        return None
    # Prefer content after the first recognised section heading through the footer-ish markers.
    start = _DETAIL_SECTION_RE.search(body)
    if not start:
        return None
    chunk = body[start.start() :]
    for stopper in (
        "Email To A Friend",
        "Print Version",
        "Openings as of",
        "postingsList",
        "</body>",
    ):
        idx = chunk.lower().find(stopper.lower())
        if idx > 200:
            chunk = chunk[:idx]
            break
    text = strip_html(chunk)
    text = collapse_ws(text)
    if len(text) < 80:
        return None
    return text[:12000]


def _wants_detail(title: str) -> bool:
    key = title.lower()
    return any(hint in key for hint in _DETAIL_TITLE_HINTS)


class AppliTrackAdapter(SourceAdapter):
    source_name = "applitrack"
    source_type = SourceType.HTML
    supported_regions = ("US",)

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        # Feeds are often multi-MB; allow a longer timeout than the global default.
        client = HttpClient()
        delay = self.config.get("request_delay_seconds", 1.5)
        timeout = float(self.config.get("request_timeout_seconds") or 90)
        max_detail = int(self.config.get("max_detail_fetches_per_tenant") or 40)
        fetch_details = bool(self.config.get("fetch_details", True))
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
                detail_fetches = 0
                for item in extract_applitrack_jobs(html):
                    item["_company"] = company
                    item["_slug"] = slug
                    item["_location_hint"] = location_hint
                    if (
                        fetch_details
                        and detail_fetches < max_detail
                        and _wants_detail(str(item.get("title") or ""))
                    ):
                        detail_url = (
                            f"https://www.applitrack.com/{slug}/onlineapp/jobpostings/"
                            f"Output.asp?AppliTrackJobId={item['id']}"
                            f"&AppliTrackLayoutMode=detail&AppliTrackViewPosting=1"
                        )
                        try:
                            detail_html = client.get_text(
                                detail_url, delay=delay, timeout=timeout
                            )
                            detail_text = extract_applitrack_detail_text(detail_html)
                            if detail_text:
                                item["description_text"] = detail_text
                            # Missing / unparseable detail stays unknown — do not invent.
                        except Exception as exc:  # noqa: BLE001
                            logger.debug(
                                "AppliTrack detail fetch failed slug=%s id=%s: %s",
                                slug,
                                item.get("id"),
                                type(exc).__name__,
                            )
                        detail_fetches += 1
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
        posted_location = payload.get("location")
        location_hint = payload.get("_location_hint")
        # Keep the posted campus/TBD text; geo resolution uses location_hint separately.
        location_text = posted_location or location_hint
        posted_raw = payload.get("date_posted")
        date_posted = parse_datetime(posted_raw) if posted_raw else None
        if date_posted is None and isinstance(posted_raw, str) and posted_raw:
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

        description_text = payload.get("description_text")

        return RawJobRecord(
            source_name=f"applitrack:{slug}",
            source_type=self.source_type,
            source_job_id=jid,
            source_url=apply,
            title=str(payload.get("title") or ""),
            company=payload.get("_company"),
            description_text=description_text,
            location_text=str(location_text) if location_text else None,
            work_mode_hint="onsite",
            date_posted=date_posted,
            closing_date=closing_date,
            apply_url=apply,
            direct_employer_url=apply,
            raw_payload={
                "closing_text": closing,
                "location_hint": location_hint,
                "posted_location": posted_location,
                "detail_fetched": bool(description_text),
            },
            source_preference=SourcePreference.EMPLOYER_CAREER,
        )
