from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Enterprise GraphRAG Intelligence Engine"
    environment: str = "development"

    # LLM Configuration
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Database URLs & Credentials
    postgres_url: str
    qdrant_url: str
    qdrant_api_key: str | None = None
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    redis_url: str

    # SaaS Multi-Tenancy & Security
    master_admin_key: str = "grag_master_admin_secret_key_2026"
    default_dev_api_key: str = "grag_dev_tenant_default_key_2026"
    default_tenant_id: str = "default_tenant"

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
