"""MEAP Application Settings.

Typed configuration hierarchy (Section 55):
    Code defaults → Environment configuration → Deployment configuration

Secrets never live in module metadata.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MEAP_",
        extra="ignore",
    )

    # -- Deployment profile (Section 57) ---------------------------------
    profile: Literal["local", "development", "test", "production"] = "local"

    # -- Application ------------------------------------------------------
    app_name: str = "Reference App"#"MEAP"
    debug: bool = False
    secret_key: str = "dev-secret-change-in-production"

    # -- Database ---------------------------------------------------------
    database_url: str = "sqlite:///./meap.db"

    # -- Artifacts / Storage (Section 35-38) ------------------------------
    artifact_storage_backend: Literal["local"] = "local"
    artifact_storage_path: str = "./artifacts"

    # -- Worker / Queue (Section 32) -------------------------------------
    # When redis_url is empty, jobs run via FastAPI BackgroundTasks (local dev).
    # When set, jobs are enqueued to RQ (Redis Queue) for distributed processing.
    redis_url: str = ""

    # -- Authentication (Section 40) -------------------------------------
    auth_enabled: bool = True #False

    # -- Diagnostics (Section 48) ----------------------------------------
    developer_area_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor for settings."""
    return Settings()
