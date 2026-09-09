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
    "remote learning",
    "remote instruction",
    "remote student",
    "remote students",
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
    r"\bvirtual teacher\b",
    r"\bvirtual tutor\b",
    r"\bonline teacher\b",
    r"\bonline tutor\b",
    r"\bonline instructor\b",
    r"\bremote teacher\b",
    r"\bremote tutor\b",
)
_TITLE_REMOTE = (
    r"\bvirtual\b",
    r"\bonline\b",
    r"\bremote\b",
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


def _title_implies_remote(title: str) -> bool:
    key = normalise_key(title)
    return any(re.search(pattern, key) for pattern in _TITLE_REMOTE)


def _country_only_location(location: str | None) -> bool:
    if not location:
        return True
    key = normalise_key(location)
    if re.search(r"\b(remote|worldwide|work from anywhere|anywhere)\b", key):
        return True
    # Country / region labels without a city (e.g. "United States", "USA", "Texas, United States").
    from job_scout.services.geo import country_from_text

    if country_from_text(location) is None:
        return False
    # Has an explicit city-like comma pattern "City, ST" → not country-only.
    if re.search(r"[a-z]{3,},\s*[a-z]{2}\b", key) and not re.search(
        r"\b(united states|usa|u\.s\.a\.|u\.s\.)\b", key
    ):
        return False
    if re.search(r"\b(united states|usa|u\.s\.a\.|u\.s\.|uk|united kingdom|canada|australia)\b", key):
        # "Austin, TX, United States" has a city token before the country.
        if re.search(r"[a-z]{3,},\s*(tx|fl|ga|al|tn|sc|nc|ky|co|ca|ny|il|oh|wa|az|nv|or|va|mo)\b", key):
            return False
        return True
    return False


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
    title_key = normalise_key(title)
    hybrid = any(re.search(pattern, blob) for pattern in _HYBRID_HINTS)
    remote = any(re.search(pattern, blob) for pattern in _REMOTE_HINTS) or _title_implies_remote(title)
    onsite = any(re.search(pattern, blob) for pattern in _ONSITE_HINTS)

    if hint == WorkMode.HYBRID or hybrid:
        return WorkMode.HYBRID
    if remote:
        if onsite and not hybrid:
            return WorkMode.HYBRID
        return WorkMode.REMOTE
    if hint == WorkMode.REMOTE:
        location_key = normalise_key(location or "")
        if _title_implies_remote(title):
            return WorkMode.REMOTE
        # Board-level "remote" + country-only location stays remote.
        if _country_only_location(location) and not onsite:
            return WorkMode.REMOTE
        # Board-level "remote" alone must not tag a Cape Town / Denver office post as WFH.
        if location_key and not re.search(r"\bremote\b", location_key):
            if onsite:
                return WorkMode.ONSITE
            if _location_implies_onsite(location) and not _country_only_location(location):
                return WorkMode.UNKNOWN
            return WorkMode.REMOTE
        if onsite and not hybrid:
            return WorkMode.HYBRID
        return WorkMode.REMOTE
    if hint == WorkMode.ONSITE or onsite:
        return WorkMode.ONSITE
    if re.search(r"\bremote\b", blob) and not onsite:
        # Bare "Remote – US residents only" is still remote work.
        if re.search(r"\bremote\b", title_key) or re.search(r"\bremote\b", normalise_key(location or "")):
            return WorkMode.REMOTE
        # Description-only "remote" is weaker; keep unknown rather than over-classify.
        if re.search(r"(this role is remote|position is remote|remote position)", blob):
            return WorkMode.REMOTE
        # Pedagogy phrases already scrubbed; remaining description-only remote → unknown,
        # then fall through to city/country onsite when applicable.
        if _location_implies_onsite(location):
            return WorkMode.ONSITE
        return WorkMode.UNKNOWN
    # Online/virtual titles already returned REMOTE above. City HQ alone is onsite.
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
