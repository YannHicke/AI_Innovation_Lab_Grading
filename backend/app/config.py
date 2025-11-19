from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration pulled from environment variables."""

    database_url: str = "sqlite:///./grader.db"
    allowed_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    share_results_default: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "APP_"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
