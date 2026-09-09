from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from job_scout.models.enums import (
    FitCategory,
    RemoteScope,
    SourcePreference,
    SourceType,
    WorkMode,
)


class RawJobRecord(BaseModel):
    """Source-local payload. Adapters emit this and nothing richer."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_type: SourceType
    source_job_id: str
    source_url: str
    title: str
    company: str | None = None
    description_html: str | None = None
    description_text: str | None = None
    location_text: str | None = None
    work_mode_hint: str | None = None
    salary_text: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    date_posted: datetime | None = None
    closing_date: date | None = None
    apply_url: str | None = None
    direct_employer_url: str | None = None
    remote_countries: list[str] = Field(default_factory=list)
    timezone_restrictions: list[str] = Field(default_factory=list)
    visa_sponsorship: bool | None = None
    relocation_assistance: bool | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    source_preference: SourcePreference = SourcePreference.AGGREGATOR


class MobilityFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visa_sponsorship: bool | None = None
    relocation_assistance: bool | None = None
    work_right_required: bool | None = None
    citizenship_required: bool | None = None
    security_clearance_required: bool | None = None
    professional_registration_required: bool | None = None
    work_authorisation_notes: str | None = None
    unknown: bool = True


class SalarySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    published: bool = False
    raw_text: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    currency: str | None = None
    period: str | None = None
    hours_per_week: Decimal | None = None
    employment_basis: str | None = None  # hourly | monthly_fixed | annual | daily | weekly
    min_monthly: Decimal | None = None
    max_monthly: Decimal | None = None
    usd_monthly: Decimal | None = None
    fx_stale: bool = False
    estimated: bool = False
    monthly_from_hours: bool = False  # True only when monthly was derived from stated hours
    parse_notes: list[str] = Field(default_factory=list)


class GeoSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    remote_scope: RemoteScope = RemoteScope.UNKNOWN
    remote_country_restrictions: list[str] = Field(default_factory=list)
    timezone_restrictions: list[str] = Field(default_factory=list)
    remote_eligibility_unknown: bool = True


class NormalisedJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: RawJobRecord
    title: str
    company: str | None = None
    company_normalised: str | None = None
    description: str = ""
    work_mode: WorkMode = WorkMode.UNKNOWN
    geo: GeoSnapshot
    salary: SalarySnapshot
    mobility: MobilityFlags
    date_posted: datetime | None = None
    closing_date: date | None = None
    apply_url: str | None = None
    direct_employer_url: str | None = None
    fingerprint: str
    rejection_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    professional_relevance: float = 0
    skills: float = 0
    seniority: float = 0
    sector: float = 0
    leadership_pm: float = 0
    digital_transferability: float = 0
    operations_alt: float = 0
    compensation: float = 0
    work_mode: float = 0
    international_mobility: float = 0
    penalties: float = 0


class CanonicalJobRecord(BaseModel):
    """Persisted shape. Source-specific fields do not belong here."""

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    canonical_fingerprint: str
    title: str
    company: str | None = None
    company_normalised: str | None = None
    description: str = ""
    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    work_mode: WorkMode
    remote_scope: RemoteScope = RemoteScope.UNKNOWN
    remote_country_restrictions: list[str] = Field(default_factory=list)
    timezone_restrictions: list[str] = Field(default_factory=list)
    salary: SalarySnapshot
    mobility: MobilityFlags
    date_posted: datetime | None = None
    closing_date: date | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    active: bool = True
    fit_score: int | None = None
    fit_category: FitCategory | None = None
    score_breakdown: ScoreBreakdown | None = None
    fit_reasons: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    last_notified_at: datetime | None = None
    apply_url: str | None = None
    direct_employer_url: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    digest_pending_update: bool = False
    rejected: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)


class JobSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_job_id: str
    source_url: str
    direct_employer_url: str | None = None
    source_preference: SourcePreference = SourcePreference.AGGREGATOR


class FilterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class PipelineStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline: str
    sources_checked: int = 0
    sources_failed: int = 0
    raw_jobs: int = 0
    relevant: int = 0
    new: int = 0
    updated: int = 0
    rejected: int = 0
    rejected_salary: int = 0
    rejected_geo: int = 0
    duplicates_merged: int = 0
    parse_errors: int = 0
    dropped_work_mode: int = 0
    failures: list[str] = Field(default_factory=list)


class HttpUrlStr(BaseModel):
    url: HttpUrl
