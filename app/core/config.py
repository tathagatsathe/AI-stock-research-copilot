from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="AI Stock Analysis API")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    api_v1_prefix: str = Field(default="/api/v1")
    log_level: str = Field(default="INFO")
    langgraph_enabled: bool = Field(default=False)
    llm_synthesis_enabled: bool = Field(default=False)
    ollama_base_url: str = Field(default="http://127.0.0.1:11434")
    ollama_model: str = Field(default="llama3.2")
    ollama_timeout_seconds: float = Field(default=30.0, gt=0)
    cache_enabled: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=86400, gt=0)
    redis_url: str = Field(default="")
    rag_enabled: bool = Field(default=True)
    rag_top_k: int = Field(default=4, ge=1, le=20)
    chroma_persist_dir: str = Field(default="data/chroma")
    stock_analysis_timeout_seconds: float = Field(default=8.0, gt=0)
    stock_universe_timeout_seconds: float = Field(default=60.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
