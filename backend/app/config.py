from functools import lru_cache
from typing import List, Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration pulled from environment variables."""

    database_url: str = "sqlite:///./grader.db"
    allowed_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    share_results_default: bool = True
    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_model: Optional[str] = None  # optional global override
    llm_model_openai: str = "gpt-4o-mini"
    llm_model_anthropic: str = "claude-sonnet-4-20250514"
    llm_base_url: Optional[str] = None
    anthropic_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 12000
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_prefix = "APP_"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
