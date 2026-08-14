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
    # Local TOTP is deliberately self-contained: no SMTP or external IdP.
    auth_enabled: bool = True
    auth_method: Literal["local_totp"] = "local_totp"
    admission_mode: Literal["invite_only", "disabled"] = "invite_only"
    allowed_email_domains: str = ""
    session_lifetime_minutes: int = 480
    session_absolute_lifetime_hours: int = 24
    enrollment_lifetime_minutes: int = 15

    # These defaults are development-only. Production startup rejects them.
    session_hmac_key: str = "local-session-hmac-key-change-before-production"
    csrf_key: str = "local-csrf-key-change-before-production"
    token_hmac_key: str = "local-token-hmac-key-change-before-production"
    credential_encryption_key: str = "4G9HkM4pV4C2u_uMaY-7z8s8Q-OHN34JOj0H6jOO1V0="
    credential_encryption_keys: str = ""
    credential_encryption_key_id: str = "local-v1"

    # -- Notebook registry -----------------------------------------------
    # Phase 1 is metadata only. Enabling this flag does not start, proxy,
    # embed, or execute Marimo/Jupyter processes.
    notebooks_enabled: bool = False

    # -- Diagnostics (Section 48) ----------------------------------------
    developer_area_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor for settings."""
    return Settings()
