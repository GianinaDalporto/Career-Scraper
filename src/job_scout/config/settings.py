"""Environment + YAML configuration. Credentials never live in YAML."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "config").exists():
            return candidate
    return current


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    resend_api_key: str = ""
    resend_from: str = ""
    digest_to: str = ""

    usajobs_api_key: str = ""
    usajobs_user_agent: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    job_scout_env: str = "local"
    job_scout_log_level: str = "INFO"
    job_scout_user_agent: str = "JobScout/1.0 (personal job search)"
    job_scout_dry_run: bool = False
    job_scout_send_email: bool = False
    job_scout_live: bool = False
    job_scout_config_dir: str = "config"

    request_timeout_seconds: float = 25.0
    request_retries: int = 3
    request_backoff_seconds: float = 1.5
    max_pages_per_source: int = 4
    max_job_age_days: int = 45
    fx_base_currency: str = "USD"

    def config_dir(self) -> Path:
        path = Path(self.job_scout_config_dir)
        if path.is_absolute():
            return path
        return find_project_root() / path

    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def has_resend(self) -> bool:
        return bool(self.resend_api_key and self.resend_from and self.digest_to)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_yaml(name: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = settings.config_dir() / name
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_profile(settings: Settings | None = None) -> dict[str, Any]:
    return load_yaml("profile.yaml", settings)


def load_salary_policy(settings: Settings | None = None) -> dict[str, Any]:
    return load_yaml("salary_policy.yaml", settings)


def load_sources(settings: Settings | None = None) -> dict[str, Any]:
    return load_yaml("sources.yaml", settings)


def load_scoring(settings: Settings | None = None) -> dict[str, Any]:
    return load_yaml("scoring.yaml", settings)


def clear_settings_cache() -> None:
    get_settings.cache_clear()
