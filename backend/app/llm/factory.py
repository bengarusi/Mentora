from functools import lru_cache

from app.core.config import settings
from app.llm.provider import LLMProvider


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """Selects the LLM implementation. The seam that lets tests inject a fake
    and lets a future provider drop in without touching call sites.

    Cached so the provider (and its underlying HTTP connection pool) is built
    once and reused across requests, instead of paying a fresh TLS handshake on
    every LLM call."""
    if settings.LLM_PROVIDER == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
