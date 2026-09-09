"""Shared HTTP, JSON, RSS and HTML helpers. Rate-limited and retried."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import httpx
from bs4 import BeautifulSoup

from job_scout.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def redact_url(url: str) -> str:
    """Strip query/fragment so API keys in query strings never hit logs."""
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:  # noqa: BLE001
        return "<redacted-url>"


class HttpClient:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        *,
        allowed_hosts: set[str] | None = None,
        max_bytes: int | None = None,
        follow_redirects: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.allowed_hosts = {h.lower() for h in (allowed_hosts or set())}
        self.max_bytes = max_bytes
        headers = {"User-Agent": self.settings.job_scout_user_agent, "Accept": "*/*"}
        self._owns = client is None
        self.client = client or httpx.Client(
            timeout=self.settings.request_timeout_seconds,
            headers=headers,
            follow_redirects=follow_redirects,
        )
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._owns:
            self.client.close()

    def _wait(self, delay: float) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def _assert_host_allowed(self, url: str) -> None:
        if not self.allowed_hosts:
            return
        host = (urlsplit(url).hostname or "").lower()
        if host not in self.allowed_hosts:
            raise ValueError(f"Host not allowlisted for fetch: {host or '<none>'}")

    def request(
        self,
        method: str,
        url: str,
        *,
        delay: float = 1.0,
        retries: int | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        self._assert_host_allowed(url)
        retries = self.settings.request_retries if retries is None else retries
        backoff = self.settings.request_backoff_seconds
        last_exc: Exception | None = None
        safe_url = redact_url(url)
        for attempt in range(retries + 1):
            self._wait(delay)
            try:
                response = self.client.request(method, url, **kwargs)
                self._last_request_at = time.monotonic()
                if self.allowed_hosts:
                    final_host = (response.url.host or "").lower()
                    if final_host and final_host not in self.allowed_hosts:
                        raise ValueError(f"Redirect left allowlist: {final_host}")
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    response.raise_for_status()
                if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    time.sleep(backoff * (2**attempt))
                    continue
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "HTTP %s %s failed (attempt %s): %s",
                    method,
                    safe_url,
                    attempt + 1,
                    type(exc).__name__,
                )
                if attempt < retries:
                    time.sleep(backoff * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("GET", url, **kwargs)
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from {redact_url(url)}") from exc

    def post_json(self, url: str, payload: dict[str, Any], **kwargs: Any) -> Any:
        response = self.request("POST", url, json=payload, **kwargs)
        return response.json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.request("GET", url, **kwargs).text

    def get_rss(self, url: str, **kwargs: Any) -> list[dict[str, Any]]:
        parsed = feedparser.parse(self.get_text(url, **kwargs))
        entries = []
        for entry in parsed.entries:
            entries.append(dict(entry))
        return entries

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        response = self.request("GET", url, **kwargs)
        content = response.content
        if self.max_bytes is not None and len(content) > self.max_bytes:
            raise ValueError(f"Response exceeds max_bytes={self.max_bytes}")
        return content

    def get_soup(self, url: str, **kwargs: Any) -> BeautifulSoup:
        return BeautifulSoup(self.get_text(url, **kwargs), "lxml")


def abs_url(base: str, maybe: str | None) -> str | None:
    if not maybe:
        return None
    return urljoin(base, maybe)


def paginate_offset(start: int, step: int, max_pages: int) -> list[int]:
    return [start + step * page for page in range(max_pages)]
