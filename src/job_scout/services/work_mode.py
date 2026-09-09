"""Classify work mode without treating every occurrence of 'remote' as WFH."""

from __future__ import annotations

import re

from job_scout.models.enums import WorkMode
from job_scout.models.job import RawJobRecord
from job_scout.utils.text import normalise_key

_FALSE_REMOTE = (
    "remote sensing",
    "remote village",
    "remote site",
    "remote area",
    "remote dam",
    "remote plant",
    "remote location work",
    "remote communities",
    "remote camp",
    "fly in fly out",
    "fifo",
)

_HYBRID_HINTS = (
    r"\bhybrid\b",
    r"\b\d\s*days?\s+in\s+(office|site)\b",
    r"\bpartially remote\b",
    r"\boffice\s*/\s*remote\b",
)
_REMOTE_HINTS = (
    r"\bfully remote\b",
    r"\b100%\s*remote\b",
    r"\bremote[ -]?first\b",
    r"\bwork from home\b",
    r"\bwfh\b",
    r"\bwork from anywhere\b",
    r"\bdistributed team\b",
)
_ONSITE_HINTS = (
    r"\bon[ -]?site\b",
    r"\bonsite\b",
    r"\bin[ -]?office\b",
    r"\bin[ -]?person\b",
    r"\bsite based\b",
    r"\boffice based\b",
    r"\bmust be (located|based) in\b",
)


def _scrub_false_remote(text: str) -> str:
    cleaned = text
    for phrase in _FALSE_REMOTE:
        cleaned = cleaned.replace(phrase, " ")
    return cleaned


def classify_work_mode(
    *,
    title: str,
    description: str,
    location: str | None,
    source_hint: str | None,
) -> WorkMode:
    hint = normalise_key(source_hint)
    if hint in {WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE}:
        # Still inspect text: a "remote" board can host hybrid/onsite labels.
        pass

    blob = _scrub_false_remote(normalise_key(" ".join(filter(None, [title, location, description, source_hint]))))
    hybrid = any(re.search(pattern, blob) for pattern in _HYBRID_HINTS)
    remote = any(re.search(pattern, blob) for pattern in _REMOTE_HINTS)
    onsite = any(re.search(pattern, blob) for pattern in _ONSITE_HINTS)

    if hint == WorkMode.HYBRID or hybrid:
        return WorkMode.HYBRID
    if remote:
        if onsite and not hybrid:
            return WorkMode.HYBRID
        return WorkMode.REMOTE
    if hint == WorkMode.REMOTE:
        location_key = normalise_key(location or "")
        # Board-level "remote" alone must not tag a Cape Town / Denver office post as WFH.
        if location_key and not re.search(r"\bremote\b", location_key):
            if onsite:
                return WorkMode.ONSITE
            return WorkMode.UNKNOWN
        if onsite and not hybrid:
            return WorkMode.HYBRID
        return WorkMode.REMOTE
    if hint == WorkMode.ONSITE or onsite:
        return WorkMode.ONSITE
    if re.search(r"\bremote\b", blob) and not onsite:
        # Bare "Remote – US residents only" is still remote work.
        if re.search(r"\bremote\b", normalise_key(title)) or re.search(r"\bremote\b", normalise_key(location or "")):
            return WorkMode.REMOTE
        # Description-only "remote" is weaker; keep unknown rather than over-classify.
        if re.search(r"(this role is remote|position is remote|remote position)", blob):
            return WorkMode.REMOTE
        return WorkMode.UNKNOWN
    # Office ATS posts often omit "on-site" wording but list a real city/country.
    if _location_implies_onsite(location):
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def _location_implies_onsite(location: str | None) -> bool:
    if not location:
        return False
    from job_scout.services.geo import country_from_text

    key = normalise_key(location)
    if re.search(r"\b(remote|worldwide|work from anywhere|anywhere)\b", key):
        return False
    return country_from_text(location) is not None


def classify_from_raw(raw: RawJobRecord, description: str) -> WorkMode:
    return classify_work_mode(
        title=raw.title,
        description=description,
        location=raw.location_text,
        source_hint=raw.work_mode_hint,
    )
