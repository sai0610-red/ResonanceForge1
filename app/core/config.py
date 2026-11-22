"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
SUPPORTED_PROVIDERS = ("groq", "bedrock")


class Settings(BaseSettings):
    """ResonanceForge configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # groq (default) | bedrock. Bedrock uses the default AWS credential chain
    # (ECS task role, instance profile, AWS_PROFILE); no AWS keys are read here.
    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    bedrock_model_id: str = Field(default="openai.gpt-oss-120b-1:0", alias="BEDROCK_MODEL_ID")
    aws_region: str = Field(default="us-west-2", alias="AWS_REGION")
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
    # Which X-Forwarded-For entry to trust when TRUSTED_PROXY=true: "first"
    # (Fly, Railway overwrite the header) or "last" (AWS ALB appends to it).
    trusted_proxy_hop: str = Field(default="first", alias="TRUSTED_PROXY_HOP")
    # Comma-separated origins. Empty means CORS middleware is not installed
    # (same-origin UI does not need it).
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_seconds: float = Field(
        default=1.0, alias="LLM_RETRY_BACKOFF_SECONDS"
    )
    # Total seconds to wait across rate-limit (429) retries for one LLM call.
    # Honors the provider's Retry-After / "try again in Xs" hint. 0 disables.
    llm_rate_limit_budget_seconds: float = Field(
        default=90.0, alias="LLM_RATE_LIMIT_BUDGET_SECONDS"
    )
    # Optional model tried once after rate-limit retries are exhausted
    # (e.g. openai/gpt-oss-20b, which has its own quota on Groq). Empty = off.
    llm_fallback_model: str = Field(default="", alias="LLM_FALLBACK_MODEL")
    # The critic sees the generated code; cap it so one request fits a free-tier
    # tokens-per-minute budget.
    critic_max_code_chars: int = Field(default=8000, alias="CRITIC_MAX_CODE_CHARS")
    # Optional customer-document grounding (POST /api/documents).
    rag_max_files: int = Field(default=5, alias="RAG_MAX_FILES")
    rag_max_file_bytes: int = Field(default=2_000_000, alias="RAG_MAX_FILE_BYTES")
    rag_max_total_chars: int = Field(default=300_000, alias="RAG_MAX_TOTAL_CHARS")
    rag_chunk_chars: int = Field(default=800, alias="RAG_CHUNK_CHARS")
    rag_chunk_overlap: int = Field(default=120, alias="RAG_CHUNK_OVERLAP")
    # Passages per agent prompt. 4 x ~800 chars is ~800 tokens on the free tier.
    rag_top_k: int = Field(default=4, alias="RAG_TOP_K")
    upload_rate_limit_per_hour: int = Field(default=20, alias="UPLOAD_RATE_LIMIT_PER_HOUR")

    @property
    def provider(self) -> str:
        """Normalized LLM_PROVIDER. Raises ValueError for unknown values."""
        value = (self.llm_provider or "groq").strip().lower()
        if value not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"LLM_PROVIDER must be one of {', '.join(SUPPORTED_PROVIDERS)}; got {value!r}"
            )
        return value

    @property
    def active_model(self) -> str:
        """Model id for the configured provider (shown on /health; no secrets)."""
        return self.bedrock_model_id if self.provider == "bedrock" else self.groq_model

    def llm_config_error(self) -> str | None:
        """Human-readable reason the LLM cannot be called, or None when configured."""
        try:
            provider = self.provider
        except ValueError as exc:
            return str(exc)
        if provider == "groq" and not (self.groq_api_key or "").strip():
            return "GROQ_API_KEY is missing. Copy .env.example to .env and set GROQ_API_KEY."
        if provider == "bedrock":
            if not (self.bedrock_model_id or "").strip():
                return "LLM_PROVIDER=bedrock but BEDROCK_MODEL_ID is empty."
            if not (self.aws_region or "").strip():
                return "LLM_PROVIDER=bedrock but AWS_REGION is empty."
        return None

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
        provider = self.provider  # unknown LLM_PROVIDER fails at startup in any env
        if not self.is_production:
            return
        required = [("DEMO_TOKEN", self.demo_token)]
        if provider == "groq":
            required.insert(0, ("GROQ_API_KEY", self.groq_api_key))
        else:
            required += [("BEDROCK_MODEL_ID", self.bedrock_model_id), ("AWS_REGION", self.aws_region)]
        missing = [name for name, value in required if not (value or "").strip()]
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
