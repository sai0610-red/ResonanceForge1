"""LLM factory for ResonanceForge agents."""

from langchain_groq import ChatGroq

from app.core.config import get_settings


def get_llm() -> ChatGroq:
    """Return a ChatGroq client configured from settings."""
    settings = get_settings()
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.temperature,
    )
