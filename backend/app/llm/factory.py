from app.core.config import settings
from app.llm.provider import LLMProvider


def get_llm_provider() -> LLMProvider:
    """Selects the LLM implementation. The seam that lets tests inject a fake
    and lets a future provider drop in without touching call sites."""
    if settings.LLM_PROVIDER == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
