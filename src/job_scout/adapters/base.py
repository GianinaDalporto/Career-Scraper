"""Source adapter contract. Adapters fetch and parse only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from job_scout.models.enums import SourceType
from job_scout.models.job import RawJobRecord


class SourceAdapter(ABC):
    source_name: str
    source_type: SourceType
    supported_regions: tuple[str, ...] = ("global",)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def fetch_jobs(self) -> Iterable[RawJobRecord]:
        """Yield raw jobs. Must not score, dedupe, email, or write SQL."""

    def parse_job(self, payload: dict[str, Any]) -> RawJobRecord:
        raise NotImplementedError

    def health_check(self) -> dict[str, Any]:
        return {"source": self.source_name, "ok": True}

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))
