import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    tinyfish_api_key: str = os.getenv("TINYFISH_API_KEY", "")
    tinyfish_base_url: str = os.getenv(
        "TINYFISH_BASE_URL", "https://agent.tinyfish.ai"
    )
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    mock_site_base_url: str = os.getenv("MOCK_SITE_BASE_URL", "")
    token_ttl_seconds: int = int(os.getenv("TOKEN_TTL_SECONDS", "180"))
    flow_mode: str = os.getenv("FLOW_MODE", "dummy")


settings = Settings()
