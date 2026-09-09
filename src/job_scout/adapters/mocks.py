"""Fixture-backed mock adapters used in tests. They never hit the network."""

from __future__ import annotations

from typing import Any, Iterable

from job_scout.adapters.base import SourceAdapter
from job_scout.models.enums import SourcePreference, SourceType
from job_scout.models.job import RawJobRecord
from job_scout.utils.dates import parse_datetime
from job_scout.utils.text import strip_html


class MockApiAdapter(SourceAdapter):
    source_name = "mock_api"
    source_type = SourceType.API

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        for item in self.config.get("jobs") or []:
            yield self.parse_job(item)

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload["id"]),
            source_url=payload["url"],
            title=payload["title"],
            company=payload.get("company"),
            description_html=payload.get("description"),
            description_text=strip_html(payload.get("description")),
            location_text=payload.get("location"),
            work_mode_hint=payload.get("work_mode"),
            salary_text=payload.get("salary"),
            date_posted=parse_datetime(payload.get("date")),
            apply_url=payload.get("apply_url") or payload["url"],
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )


class MockRssAdapter(SourceAdapter):
    source_name = "mock_rss"
    source_type = SourceType.RSS

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        for item in self.config.get("jobs") or []:
            yield self.parse_job(item)

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id") or payload.get("link")),
            source_url=payload.get("link") or payload.get("url"),
            title=payload.get("title") or "",
            company=payload.get("company"),
            description_html=payload.get("summary"),
            description_text=strip_html(payload.get("summary")),
            location_text=payload.get("location") or "Remote",
            work_mode_hint="remote",
            date_posted=parse_datetime(payload.get("published")),
            apply_url=payload.get("link"),
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )


class MockHtmlAdapter(SourceAdapter):
    source_name = "mock_html"
    source_type = SourceType.HTML

    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        for item in self.config.get("jobs") or []:
            yield self.parse_job(item)

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        return RawJobRecord(
            source_name=self.source_name,
            source_type=self.source_type,
            source_job_id=str(payload.get("id")),
            source_url=payload.get("url"),
            title=payload.get("title") or "",
            company=payload.get("company"),
            description_html=payload.get("html"),
            description_text=strip_html(payload.get("html")),
            location_text=payload.get("location"),
            work_mode_hint=payload.get("work_mode"),
            salary_text=payload.get("salary"),
            apply_url=payload.get("url"),
            source_preference=SourcePreference.SPECIALIST_BOARD,
        )
