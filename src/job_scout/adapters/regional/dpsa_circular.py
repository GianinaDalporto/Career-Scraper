"""DPSA Public Service Vacancy Circular — weekly PDF sections (ZA government)."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable
from urllib.parse import urljoin

from job_scout.adapters.base import SourceAdapter
from job_scout.adapters.http import HttpClient
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.services.dpsa_pdf import (
    parse_circular_text,
    pdf_bytes_to_text,
    section_is_relevant,
)
from job_scout.utils.dates import utcnow

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.dpsa.gov.za/newsroom/psvc/"
BASE = "https://www.dpsa.gov.za"


class DpsaCircularAdapter(SourceAdapter):
    """Discover latest circular HTML pages, pull relevant section PDFs, parse posts."""

    source_name = "dpsa_circular"
    source_type = SourceType.HTML
    supported_regions = ("ZA",)

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        client = HttpClient(
            allowed_hosts={"www.dpsa.gov.za", "dpsa.gov.za"},
            max_bytes=20 * 1024 * 1024,
        )
        max_circulars = int(self.config.get("max_circulars", 2))
        max_jobs = int(self.config.get("max_jobs_per_source", 250))
        yielded = 0
        seen: set[str] = set()
        try:
            circular_urls = self._latest_circular_urls(client, limit=max_circulars)
            for circular_url in circular_urls:
                for pdf_url, label in self._section_pdfs(client, circular_url):
                    if yielded >= max_jobs:
                        return
                    try:
                        data = client.get_bytes(
                            pdf_url,
                            delay=self.config.get("request_delay_seconds", 1.0),
                        )
                        text = pdf_bytes_to_text(data)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("DPSA PDF failed %s: %s", pdf_url, exc)
                        continue
                    for post in parse_circular_text(
                        text,
                        source_pdf_url=pdf_url,
                        department_hint=label,
                    ):
                        if post.post_id in seen:
                            continue
                        seen.add(post.post_id)
                        yield self._to_raw(post, circular_url)
                        yielded += 1
                        if yielded >= max_jobs:
                            return
        finally:
            client.close()

    def _latest_circular_urls(self, client: HttpClient, *, limit: int) -> list[str]:
        soup = client.get_soup(INDEX_URL, delay=self.config.get("request_delay_seconds", 1.0))
        urls: list[str] = []
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            text = a.get_text(" ", strip=True)
            if re.search(r"circular-\d+-of-\d{4}", href) or re.search(
                r"Circular\s+\d+\s+of\s+\d{4}", text, re.I
            ):
                full = urljoin(BASE, href)
                if full not in urls:
                    urls.append(full)
            if len(urls) >= limit:
                break
        return urls

    def _section_pdfs(self, client: HttpClient, circular_url: str) -> list[tuple[str, str]]:
        soup = client.get_soup(circular_url, delay=self.config.get("request_delay_seconds", 1.0))
        out: list[tuple[str, str]] = []
        full_pdf: str | None = None
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            label = a.get_text(" ", strip=True) or href
            if not href.lower().endswith(".pdf"):
                continue
            full = urljoin(BASE, href)
            if "PSV" in href.upper() or "full document" in label.lower():
                full_pdf = full
                continue
            # Section PDFs look like /vacancies/2026/32/s.pdf
            if re.search(r"/vacancies/\d{4}/\d+/[a-z]\.pdf$", href, re.I) or re.search(
                r"/\d+/[a-z]\.pdf$", href, re.I
            ):
                if section_is_relevant(label):
                    out.append((full, label))
        if out:
            return out
        # Fallback: entire circular if section links missing
        if full_pdf:
            return [(full_pdf, "full circular")]
        return []

    def _to_raw(self, post: Any, circular_url: str) -> RawJobRecord:
        company = post.department_hint or "South African Public Service"
        desc = post.body
        # Unique per-post URLs so DuplicateIndex does not collapse a whole PDF into one job.
        year_match = re.search(r"/vacancies/(\d{4})/", post.source_pdf_url or "")
        year = year_match.group(1) if year_match else "unknown"
        source_job_id = f"{year}-{post.post_id}"
        post_url = f"{post.source_pdf_url}#post-{post.post_id}"
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=source_job_id,
            source_url=post_url,
            title=post.title,
            company=company,
            description_text=desc,
            description_html=None,
            location_text=(f"{post.centre}, South Africa" if post.centre else "South Africa"),
            work_mode_hint="onsite",
            salary_text=post.salary_text,
            salary_currency="ZAR",
            salary_period="annual",
            closing_date=post.closing_date,
            date_posted=utcnow(),
            apply_url=post_url,
            direct_employer_url=post_url,
            raw_payload={
                "ref_no": post.ref_no,
                "pdf": post.source_pdf_url,
                "circular": circular_url,
                "post_id": post.post_id,
            },
            source_preference=SourcePreference.GOVERNMENT,
        )
