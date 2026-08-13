from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Enterprise GraphRAG Intelligence Engine"
    environment: str = "development"

    # LLM API Key
    groq_api_key: str = ""

    # Database URLs & Credentials
    postgres_url: str
    qdrant_url: str
    qdrant_api_key: str | None = None
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    redis_url: str

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
