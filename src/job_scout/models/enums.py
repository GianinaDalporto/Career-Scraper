from __future__ import annotations

from enum import StrEnum


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class FitCategory(StrEnum):
    EXCEPTIONAL = "Exceptional"
    STRONG = "Strong"
    GOOD = "Good"
    POSSIBLE = "Possible"
    LOW = "Low"


class SourceType(StrEnum):
    API = "api"
    RSS = "rss"
    HTML = "html"
    ATS = "ats"
    BROWSER = "browser"


class PipelineName(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class RemoteScope(StrEnum):
    WORLDWIDE = "worldwide"
    ANYWHERE = "anywhere"
    GLOBAL = "global"
    EMEA = "emea"
    AFRICA = "africa"
    SOUTH_AFRICA = "south_africa"
    EUROPE = "europe"
    US_ONLY = "us_only"
    AUSTRALIA_ONLY = "australia_only"
    OTHER_RESTRICTED = "other_restricted"
    UNKNOWN = "unknown"


class JobStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class DeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    SKIPPED = "skipped"


class SourcePreference(StrEnum):
    EMPLOYER_CAREER = "employer_career"
    EMPLOYER_ATS = "employer_ats"
    GOVERNMENT = "government"
    SPECIALIST_BOARD = "specialist_board"
    AGGREGATOR = "aggregator"
