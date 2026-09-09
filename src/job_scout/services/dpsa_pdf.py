"""Parse DPSA Public Service Vacancy Circular PDF text into post records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Iterable

from pypdf import PdfReader

from job_scout.utils.dates import parse_datetime

_POST_SPLIT = re.compile(r"(?=POST\s+\d+/\d+\s*:)", re.IGNORECASE)
_POST_HEAD = re.compile(
    r"POST\s+(\d+/\d+)\s*:\s*(.+?)(?:\s+REF\s+NO\.?\s*:\s*(.+))?$",
    re.IGNORECASE | re.DOTALL,
)
_SALARY = re.compile(r"SALARY\s*:?\s*(.+?)(?=\n\s*CENTRE|\n\s*REQUIREMENTS|\n\s*DUTIES|\n\s*POST\s+\d)", re.IGNORECASE | re.DOTALL)
_CENTRE = re.compile(r"CENTRE\s*:?\s*(.+?)(?=\n\s*REQUIREMENTS|\n\s*DUTIES|\n\s*ENQUIRIES|\n\s*POST\s+\d)", re.IGNORECASE | re.DOTALL)
_CLOSING = re.compile(
    r"CLOSING\s+DATE\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE,
)
_ENGINEERING = re.compile(
    r"\b("
    r"chief\s+engineer|engineer(?:ing)?|mechanical|civil|structural|"
    r"water\s+(?:and\s+)?sanitation|hydraul(?:ic|ics)|hydrolog|"
    r"pipeline|pump(?:ing)?|dam(?:s)?|reservoir|irrigation|"
    r"infrastructure|works\s+inspector|technician\s*\(?ohs\)?|"
    r"ecsa|professional\s+engineer"
    r")\b",
    re.IGNORECASE,
)

# Section PDFs most likely to carry engineering / infra posts
DEFAULT_SECTION_HINTS = (
    "water",
    "sanitation",
    "public works",
    "infrastructure",
    "mineral",
    "petroleum",
    "human settlements",
    "cogta",
    "cooperative governance",
    "limpopo",
    "gauteng",
    "mpumalanga",
    "free state",
    "northern cape",
    "western cape",
    "kwazulu",
    "eastern cape",
    "north west",
    "defence",
    "forestry",
    "agriculture",
)


@dataclass
class DpsaPost:
    post_id: str
    title: str
    ref_no: str | None
    salary_text: str | None
    centre: str | None
    closing_date: date | None
    body: str
    source_pdf_url: str
    department_hint: str | None = None


def pdf_bytes_to_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    # Normalise PDF quirks: soft hyphens / odd spacing
    text = "\n".join(parts)
    text = text.replace("\u00ad", "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def is_engineering_relevant(title: str, body: str) -> bool:
    blob = f"{title}\n{body}"
    return bool(_ENGINEERING.search(blob))


def _clean_field(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" :-")
    return cleaned or None


def parse_circular_text(text: str, *, source_pdf_url: str, department_hint: str | None = None) -> list[DpsaPost]:
    posts: list[DpsaPost] = []
    chunks = _POST_SPLIT.split(text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.upper().startswith("POST "):
            continue
        first_line, _, rest = chunk.partition("\n")
        head = _POST_HEAD.match(first_line.strip())
        if not head:
            # Title may wrap onto next line(s) before SALARY
            head_blob = first_line
            for line in rest.splitlines()[:3]:
                if re.match(r"^(SALARY|CENTRE|REQUIREMENTS|DUTIES)\b", line.strip(), re.I):
                    break
                head_blob += " " + line.strip()
            head = _POST_HEAD.match(head_blob.strip())
        if not head:
            continue
        post_id = head.group(1).strip()
        title = _clean_field(head.group(2)) or ""
        ref_no = _clean_field(head.group(3))
        if not ref_no:
            ref_m = re.search(r"REF\s+NO\.?\s*:?\s*(.+)$", title, re.I)
            if ref_m:
                ref_no = _clean_field(ref_m.group(1))
                title = _clean_field(title[: ref_m.start()]) or title
        title = re.sub(r"\s+REF\s+NO\.?\s*:?\s*.*$", "", title, flags=re.I).strip(" :-")
        body = chunk
        if not is_engineering_relevant(title, body):
            continue
        salary_m = _SALARY.search(body)
        centre_m = _CENTRE.search(body)
        closing_m = _CLOSING.search(body)
        closing = None
        if closing_m:
            dt = parse_datetime(closing_m.group(1))
            closing = dt.date() if dt else None
        posts.append(
            DpsaPost(
                post_id=post_id,
                title=title,
                ref_no=ref_no,
                salary_text=_clean_field(salary_m.group(1) if salary_m else None),
                centre=_clean_field(centre_m.group(1) if centre_m else None),
                closing_date=closing,
                body=body[:4000],
                source_pdf_url=source_pdf_url,
                department_hint=department_hint,
            )
        )
    return posts


def section_is_relevant(label: str, hints: Iterable[str] = DEFAULT_SECTION_HINTS) -> bool:
    lowered = label.lower()
    return any(h in lowered for h in hints)
