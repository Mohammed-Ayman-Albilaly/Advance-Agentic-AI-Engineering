"""Application configuration for UniFlow AI.

Secrets and environment-specific values are loaded from environment variables or
an optional local `.env` file.  The `.env` file is excluded from Git.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="UniFlow AI", alias="APP_NAME")
    app_env: Literal["development", "test", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_path: Path = Field(default=Path("logs/uniflow.jsonl"), alias="LOG_PATH")

    database_path: Path = Field(
        default=Path("data/uniflow.sqlite"), alias="DATABASE_PATH"
    )
    checkpoint_database_path: Path = Field(
        default=Path("data/checkpoints.sqlite"), alias="CHECKPOINT_DATABASE_PATH"
    )
    max_replans: int = Field(default=3, ge=1, le=10, alias="MAX_REPLANS")

    llm_provider: Literal["not_configured", "openai"] = Field(
        default="not_configured", alias="LLM_PROVIDER"
    )
    llm_model: str = Field(default="", alias="LLM_MODEL")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")

    def ensure_runtime_directories(self) -> None:
        """Create parent directories required by SQLite persistence."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance for application runtime use."""
    settings = Settings()
    settings.ensure_runtime_directories()
    return settings
