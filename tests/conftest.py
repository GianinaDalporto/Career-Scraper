from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from job_scout.config.settings import Settings, clear_settings_cache
from job_scout.models.enums import SourcePreference, SourceType, WorkMode
from job_scout.models.job import CanonicalJobRecord, RawJobRecord, SalarySnapshot
from job_scout.services.database import InMemoryJobRepository
from job_scout.services.fx import InMemoryFxStore, FxService
from job_scout.utils.dates import utcnow

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_CONFIG_DIR", str(ROOT / "config"))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def repo() -> InMemoryJobRepository:
    return InMemoryJobRepository()


@pytest.fixture
def fx() -> FxService:
    store = InMemoryFxStore()
    service = FxService(store=store)
    today = utcnow().date()
    store.save_rate("USD", "ZAR", today, Decimal("18.00"))
    store.save_rate("USD", "EUR", today, Decimal("0.92"))
    store.save_rate("USD", "GBP", today, Decimal("0.78"))
    store.save_rate("USD", "AUD", today, Decimal("1.50"))
    store.save_rate("EUR", "USD", today, Decimal("1.09"))
    store.save_rate("ZAR", "USD", today, Decimal("0.055"))
    store.save_rate("AUD", "USD", today, Decimal("0.67"))
    store.save_rate("GBP", "USD", today, Decimal("1.28"))
    return service


def raw_job(**kwargs) -> RawJobRecord:
    base = dict(
        source_name="fixture",
        source_type=SourceType.API,
        source_job_id="1",
        source_url="https://example.com/jobs/1",
        title="Senior Mechanical Engineer",
        company="Jacobs",
        description_text="Mechanical design for dams, pipelines and pumps. QA/QC and FIDIC.",
        location_text="Cape Town, South Africa",
        work_mode_hint="onsite",
        salary_text="R80,000 per month",
        apply_url="https://example.com/jobs/1",
        source_preference=SourcePreference.EMPLOYER_ATS,
    )
    base.update(kwargs)
    return RawJobRecord(**base)


def canonical_job(**kwargs) -> CanonicalJobRecord:
    from job_scout.models.enums import RemoteScope
    from job_scout.models.job import MobilityFlags
    from job_scout.services.normalisation import fingerprint

    title = kwargs.pop("title", "Senior Mechanical Engineer")
    company = kwargs.pop("company", "Jacobs")
    city = kwargs.pop("city", "Cape Town")
    country = kwargs.pop("country_code", "ZA")
    work_mode = kwargs.pop("work_mode", WorkMode.ONSITE)
    job = CanonicalJobRecord(
        canonical_fingerprint=kwargs.pop("canonical_fingerprint", fingerprint(company, title, city, country, work_mode.value)),
        title=title,
        company=company,
        company_normalised="jacobs",
        description=kwargs.pop("description", "Mechanical design, pipelines, pumps, dams, QA/QC, FIDIC."),
        location_text=kwargs.pop("location_text", "Cape Town, South Africa"),
        city=city,
        country_code=country,
        work_mode=work_mode,
        remote_scope=kwargs.pop("remote_scope", RemoteScope.UNKNOWN),
        salary=kwargs.pop("salary", SalarySnapshot(published=True, raw_text="R80,000 pm", min_monthly=Decimal("80000"), currency="ZAR")),
        mobility=kwargs.pop("mobility", MobilityFlags(unknown=True)),
        apply_url=kwargs.pop("apply_url", "https://example.com/jobs/1"),
        **kwargs,
    )
    return job
