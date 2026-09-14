"""Base runtime configuration.

Owns the settings this story needs: the service name used in logs/app
metadata and the root log level. Later stories may extend this same
`Settings` class with DB URL / JWT settings per the Config layer's
responsibilities in specs/design/architecture.md — no speculative fields
are added here ahead of that.

Tests must isolate themselves from any real `.env` file by constructing
`Settings(_env_file=None)` explicitly (pydantic-settings convention).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Base application settings, sourced from environment variables."""

    model_config = SettingsConfigDict(env_prefix="TRUELEND_", extra="ignore")

    service_name: str = "truelend-backend"
    log_level: str = "INFO"
    # Reported by `GET /health` per the frozen api-contracts.md shape.
    version: str = "0.1.0"
