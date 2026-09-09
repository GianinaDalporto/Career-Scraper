"""Cross-platform duplicate detection. Conservative on same-company different reqs."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from job_scout.models.enums import SourcePreference
from job_scout.models.job import CanonicalJobRecord, JobSourceRef, NormalisedJobRecord
from job_scout.utils.text import company_key, normalise_key, sha256_text

PREFERENCE_RANK = {
    SourcePreference.EMPLOYER_CAREER: 0,
    SourcePreference.EMPLOYER_ATS: 1,
    SourcePreference.GOVERNMENT: 2,
    SourcePreference.SPECIALIST_BOARD: 3,
    SourcePreference.AGGREGATOR: 4,
}


def canonical_url(url: str | None) -> str:
    if not url:
        return ""
    text = url.strip().lower().split("?", 1)[0]
    # Keep fragments — DPSA posts share a PDF URL and disambiguate with #POST-id.
    if "#" in text:
        base, frag = text.split("#", 1)
        return f"{base.rstrip('/')}" + (f"#{frag}" if frag else "")
    return text.rstrip("/")


def _shared_document_url(url: str | None) -> bool:
    """True when URL is a circular/PDF/list page that many posts share (must not dedupe on it)."""
    if not url:
        return False
    lowered = url.lower().split("#", 1)[0]
    if lowered.endswith(".pdf"):
        return True
    if "dpsa.gov.za" in lowered and ("/psvc" in lowered or "/vacancies/" in lowered):
        return True
    return False


def identifier_key(source_name: str, source_job_id: str) -> str:
    return f"{source_name}:{source_job_id}".lower()


def fingerprint_from_normalised(job: NormalisedJobRecord) -> str:
    return job.fingerprint


def description_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(fuzz.token_set_ratio(a[:4000], b[:4000]))


@dataclass
class DuplicateIndex:
    by_url: dict[str, str] = field(default_factory=dict)
    by_source_id: dict[str, str] = field(default_factory=dict)
    by_fingerprint: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, CanonicalJobRecord] = field(default_factory=dict)
    sources: dict[str, list[JobSourceRef]] = field(default_factory=dict)

    def add(self, job: CanonicalJobRecord, ref: JobSourceRef) -> CanonicalJobRecord:
        match_id = self._find(job, ref)
        if match_id is None:
            key = job.canonical_fingerprint
            self.jobs[key] = job
            self.sources[key] = [ref]
            self._index(job, ref, key)
            return job
        existing = self.jobs[match_id]
        merged = merge_jobs(existing, job, self.sources[match_id], ref)
        # Always persist under the surviving index key — merge_jobs may return
        # `incoming` with a different fingerprint when an employer source outranks an aggregator.
        merged.canonical_fingerprint = match_id
        if existing.id:
            merged.id = existing.id
        self.jobs[match_id] = merged
        self.sources[match_id].append(ref)
        self._index(merged, ref, match_id)
        merged.flags = list(dict.fromkeys([*merged.flags, "duplicate_merged"]))
        return merged

    def _find(self, job: CanonicalJobRecord, ref: JobSourceRef) -> str | None:
        # Prefer source ids before shared document URLs (DPSA section PDFs, circular pages).
        ident = identifier_key(ref.source_name, ref.source_job_id)
        if ident in self.by_source_id:
            return self.by_source_id[ident]
        for url in filter(
            None,
            [
                canonical_url(ref.direct_employer_url),
                canonical_url(ref.source_url),
                canonical_url(job.apply_url),
            ],
        ):
            if _shared_document_url(url):
                continue
            if url in self.by_url:
                return self.by_url[url]
        if job.canonical_fingerprint in self.by_fingerprint:
            return self.by_fingerprint[job.canonical_fingerprint]
        for key, existing in self.jobs.items():
            if _fuzzy_duplicate(existing, job):
                return key
        return None

    def _index(self, job: CanonicalJobRecord, ref: JobSourceRef, key: str) -> None:
        for url in filter(
            None,
            [
                canonical_url(ref.direct_employer_url),
                canonical_url(ref.source_url),
                canonical_url(job.apply_url),
            ],
        ):
            if _shared_document_url(url):
                continue
            self.by_url[url] = key
        self.by_source_id[identifier_key(ref.source_name, ref.source_job_id)] = key
        self.by_fingerprint[job.canonical_fingerprint] = key


def _fuzzy_duplicate(a: CanonicalJobRecord, b: CanonicalJobRecord) -> bool:
    if company_key(a.company) != company_key(b.company):
        return False
    if a.country_code and b.country_code and a.country_code != b.country_code:
        return False
    if (a.city or "").lower() and (b.city or "").lower() and normalise_key(a.city) != normalise_key(b.city):
        return False
    if a.work_mode != b.work_mode:
        return False
    title_score = fuzz.token_set_ratio(normalise_key(a.title), normalise_key(b.title))
    if title_score < 92:
        return False
    desc = description_similarity(a.description, b.description)
    if desc < 86:
        return False
    return True


def _salary_more_complete(incoming, existing) -> bool:
    """Prefer a published salary that has more structured fields filled in."""
    def score(snap) -> int:
        return sum(
            1
            for value in (
                snap.min_monthly,
                snap.max_monthly,
                snap.min_amount,
                snap.max_amount,
                snap.currency,
                snap.period,
                snap.raw_text,
            )
            if value not in (None, "")
        )

    return score(incoming) > score(existing)


def merge_jobs(
    preferred: CanonicalJobRecord,
    incoming: CanonicalJobRecord,
    existing_refs: list[JobSourceRef],
    new_ref: JobSourceRef,
) -> CanonicalJobRecord:
    current_rank = min((PREFERENCE_RANK.get(r.source_preference, 9) for r in existing_refs), default=9)
    incoming_rank = PREFERENCE_RANK.get(new_ref.source_preference, 9)
    base, other = (incoming, preferred) if incoming_rank < current_rank else (preferred, incoming)
    if incoming.salary.published and not base.salary.published:
        base.salary = incoming.salary
    elif other.salary.published and not base.salary.published:
        base.salary = other.salary
    elif (
        incoming.salary.published
        and base.salary.published
        and incoming_rank <= current_rank
        and _salary_more_complete(incoming.salary, base.salary)
    ):
        base.salary = incoming.salary
    if incoming.direct_employer_url and not base.direct_employer_url:
        base.direct_employer_url = incoming.direct_employer_url
    if incoming.closing_date and not base.closing_date:
        base.closing_date = incoming.closing_date
    if incoming.mobility.visa_sponsorship is not None and base.mobility.visa_sponsorship is None:
        base.mobility.visa_sponsorship = incoming.mobility.visa_sponsorship
    if incoming.mobility.relocation_assistance is not None and base.mobility.relocation_assistance is None:
        base.mobility.relocation_assistance = incoming.mobility.relocation_assistance
    urls = list(dict.fromkeys([*base.source_urls, *incoming.source_urls, new_ref.source_url]))
    base.source_urls = urls
    if _description_prefer(incoming.description, base.description or ""):
        base.description = incoming.description
    return base


def _description_prefer(incoming: str, existing: str) -> bool:
    """Prefer cleaner plain text over leftover HTML / entity-encoded blobs."""

    def quality(text: str) -> int:
        if not text:
            return -1
        score = len(text)
        lowered = text.lower()
        if "&lt;" in lowered or "&gt;" in lowered or "font-family" in lowered:
            score -= 100_000
        if "<div" in lowered or "<span" in lowered or "<p>" in lowered:
            score -= 100_000
        return score

    return quality(incoming) > quality(existing)


def to_canonical(job: NormalisedJobRecord) -> CanonicalJobRecord:
    return CanonicalJobRecord(
        canonical_fingerprint=job.fingerprint or sha256_text(job.title, job.company or ""),
        title=job.title,
        company=job.company,
        company_normalised=job.company_normalised,
        description=job.description,
        location_text=job.geo.location_text,
        city=job.geo.city,
        region=job.geo.region,
        country_code=job.geo.country_code,
        work_mode=job.work_mode,
        remote_scope=job.geo.remote_scope,
        remote_country_restrictions=job.geo.remote_country_restrictions,
        timezone_restrictions=job.geo.timezone_restrictions,
        salary=job.salary,
        mobility=job.mobility,
        date_posted=job.date_posted,
        closing_date=job.closing_date,
        apply_url=job.apply_url,
        direct_employer_url=job.direct_employer_url,
        source_urls=[job.raw.source_url],
        flags=job.flags,
        rejected=bool(job.rejection_reasons),
        rejection_reasons=job.rejection_reasons,
    )


def source_ref_from(job: NormalisedJobRecord) -> JobSourceRef:
    return JobSourceRef(
        source_name=job.raw.source_name,
        source_job_id=job.raw.source_job_id,
        source_url=job.raw.source_url,
        direct_employer_url=job.raw.direct_employer_url,
        source_preference=job.raw.source_preference,
    )
