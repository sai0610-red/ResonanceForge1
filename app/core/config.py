"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """ResonanceForge configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-120b", alias="GROQ_MODEL")
    temperature: float = Field(default=0.2, alias="TEMPERATURE")
    demo_token: str = Field(default="", alias="DEMO_TOKEN")
    rate_limit_per_hour: int = Field(default=5, alias="RATE_LIMIT_PER_HOUR")
    max_situation_chars: int = Field(default=4000, alias="MAX_SITUATION_CHARS")
    data_dir: str = Field(default="./data", alias="DATA_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    env: str = Field(default="development", alias="ENV")
    # When true, rate limiting uses the first X-Forwarded-For hop. Leave false
    # unless the process sits behind a trusted proxy (Fly, Railway) that sets
    # that header. Clients can otherwise spoof the header and bypass the limit.
    trusted_proxy: bool = Field(default=False, alias="TRUSTED_PROXY")
    # Comma-separated origins. Empty means CORS middleware is not installed
    # (same-origin UI does not need it).
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_seconds: float = Field(
        default=1.0, alias="LLM_RETRY_BACKOFF_SECONDS"
    )

    @property
    def is_production(self) -> bool:
        return (self.env or "").strip().lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]

    @property
    def data_path(self) -> Path:
        """DATA_DIR as an absolute path (relative paths resolve from the project root)."""
        p = Path(self.data_dir or "./data").expanduser()
        if not p.is_absolute():
            p = ROOT / p
        return p

    def validate_for_startup(self) -> None:
        """Refuse to start in production without required secrets (values never printed)."""
        if not self.is_production:
            return
        missing = [
            name
            for name, value in (
                ("GROQ_API_KEY", self.groq_api_key),
                ("DEMO_TOKEN", self.demo_token),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise RuntimeError(
                "ENV=production but required settings are missing: "
                + ", ".join(missing)
                + ". Set them as secrets / environment variables and restart."
            )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
