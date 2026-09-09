"""Optional Playwright wrapper. HTTP adapters must not import this at module level."""

from __future__ import annotations

from typing import Any


class BrowserNotConfiguredError(RuntimeError):
    pass


def load_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserNotConfiguredError(
            "Playwright is not installed. Add the optional extra: pip install job-scout[browser]"
        ) from exc
    return sync_playwright


class BrowserSession:
    def __init__(self) -> None:
        self._playwright = None
        self._browser = None

    def __enter__(self) -> Any:
        pw = load_playwright()
        self._playwright = pw().__enter__()
        self._browser = self._playwright.chromium.launch(headless=True)
        return self._browser

    def __exit__(self, *args: object) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.__exit__(*args)
