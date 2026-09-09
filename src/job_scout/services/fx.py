"""Frankfurter FX with daily cache. Never fabricate a rate."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol

import httpx

from job_scout.config.settings import Settings, get_settings, load_salary_policy

logger = logging.getLogger(__name__)

IDENTITY = Decimal("1")


class FxStore(Protocol):
    def get_rate(self, base: str, quote: str, on: date) -> tuple[Decimal, bool] | None: ...
    def latest_rate(self, base: str, quote: str) -> tuple[Decimal, date, bool] | None: ...
    def save_rate(self, base: str, quote: str, on: date, rate: Decimal, stale: bool = False) -> None: ...


class InMemoryFxStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, date], tuple[Decimal, bool]] = {}

    def get_rate(self, base: str, quote: str, on: date) -> tuple[Decimal, bool] | None:
        return self._rows.get((base.upper(), quote.upper(), on))

    def latest_rate(self, base: str, quote: str) -> tuple[Decimal, date, bool] | None:
        matches = [
            (on, rate, stale)
            for (b, q, on), (rate, stale) in self._rows.items()
            if b == base.upper() and q == quote.upper()
        ]
        if not matches:
            return None
        on, rate, stale = max(matches, key=lambda item: item[0])
        return rate, on, stale

    def save_rate(self, base: str, quote: str, on: date, rate: Decimal, stale: bool = False) -> None:
        self._rows[(base.upper(), quote.upper(), on)] = (rate, stale)


class FxService:
    def __init__(
        self,
        store: FxStore | None = None,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.store = store or InMemoryFxStore()
        self.settings = settings or get_settings()
        self._client = client
        policy = load_salary_policy(self.settings)
        self.api_url = ((policy.get("fx") or {}).get("api_url")) or "https://api.frankfurter.dev/v1/latest"
        self._fallback_urls = [
            self.api_url,
            "https://api.frankfurter.dev/v1/latest",
            "https://api.frankfurter.app/latest",
        ]

    def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> tuple[Decimal, bool]:
        src = from_currency.upper()
        dst = to_currency.upper()
        if src == dst:
            return amount, False
        rate, stale = self.rate(src, dst)
        return (amount * rate).quantize(Decimal("0.01")), stale

    def rate(self, base: str, quote: str) -> tuple[Decimal, bool]:
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return IDENTITY, False
        today = datetime.now(timezone.utc).date()
        cached = self.store.get_rate(base, quote, today)
        if cached:
            return cached
        try:
            fetched = self._fetch(base)
        except Exception as exc:  # noqa: BLE001 — fallback is mandatory
            logger.warning("FX fetch failed (%s); using cache if present", exc)
            latest = self.store.latest_rate(base, quote)
            if latest:
                rate, _on, _stale = latest
                self.store.save_rate(base, quote, today, rate, stale=True)
                return rate, True
            raise RuntimeError(f"No FX rate available for {base}->{quote}") from exc

        rate = fetched.get(quote)
        if rate is None:
            usd = fetched.get("USD")
            if usd is None:
                latest = self.store.latest_rate(base, quote)
                if latest:
                    return latest[0], True
                raise RuntimeError(f"Frankfurter did not return {quote}")
            usd_quote = self.rate("USD", quote)
            converted = (usd_quote[0] / usd) if base != "USD" else usd_quote[0]
            self.store.save_rate(base, quote, today, converted)
            return converted, usd_quote[1]
        decimal_rate = Decimal(str(rate))
        self.store.save_rate(base, quote, today, decimal_rate)
        for code, value in fetched.items():
            self.store.save_rate(base, code, today, Decimal(str(value)))
        return decimal_rate, False

    def refresh_usd_basket(self) -> None:
        self.rate("USD", "ZAR")

    def _fetch(self, base: str) -> dict[str, Decimal]:
        client = self._client or httpx.Client(timeout=20, follow_redirects=True)
        owns = self._client is None
        last_exc: Exception | None = None
        try:
            for url in list(dict.fromkeys(self._fallback_urls)):
                try:
                    response = client.get(url, params={"base": base})
                    if response.status_code >= 400:
                        last_exc = httpx.HTTPStatusError(
                            f"{response.status_code} for {url}",
                            request=response.request,
                            response=response,
                        )
                        continue
                    payload = response.json()
                    rates = payload.get("rates") or {}
                    if rates:
                        return {str(code).upper(): Decimal(str(value)) for code, value in rates.items()}
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    continue
        finally:
            if owns:
                client.close()
        raise RuntimeError("Frankfurter FX request failed") from last_exc
