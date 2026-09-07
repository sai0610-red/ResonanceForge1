"""Application settings loaded from environment / .env."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """ResonanceForge configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = Field(..., alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-120b", alias="GROQ_MODEL")
    temperature: float = Field(default=0.2, alias="TEMPERATURE")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance. Raises ValidationError if GROQ_API_KEY missing."""
    return Settings()
