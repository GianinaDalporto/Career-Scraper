from datetime import timedelta
from decimal import Decimal

from job_scout.services.fx import FxService, InMemoryFxStore
from job_scout.utils.dates import utcnow


def test_identity_rate():
    fx = FxService(store=InMemoryFxStore())
    amount, stale = fx.convert(Decimal("10"), "USD", "USD")
    assert amount == Decimal("10")
    assert stale is False


def test_stale_cache_used_when_fetch_fails():
    store = InMemoryFxStore()
    yesterday = utcnow().date() - timedelta(days=1)
    store.save_rate("USD", "ZAR", yesterday, Decimal("18.5"))

    class Dead(FxService):
        def _fetch(self, base: str):
            raise RuntimeError("network down")

    fx = Dead(store=store)
    rate, stale = fx.rate("USD", "ZAR")
    assert rate == Decimal("18.5")
    assert stale is True
