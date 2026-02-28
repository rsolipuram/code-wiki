from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    secret_key: str = Field(default="dev-secret-key-change-in-production", alias="SECRET_KEY")

    # PostgreSQL
    database_url: str = Field(
        default="postgresql://codewiki:codewiki@localhost:5432/codewiki",
        alias="DATABASE_URL",
    )

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="codewiki", alias="NEO4J_PASSWORD")

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")

    # LLM (LM Studio)
    llm_provider: str = Field(default="lmstudio", alias="LLM_PROVIDER")
    llm_base_url: str = Field(default="http://localhost:1234/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="Qwen2.5-Coder-7B-Instruct", alias="LLM_MODEL")
    llm_api_key: str = Field(default="not-needed", alias="LLM_API_KEY")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

    # Repository storage
    repo_cache_dir: str = Field(default="./cache/repos", alias="REPO_CACHE_DIR")

    # Performance
    max_concurrent_parses: int = Field(default=5, alias="MAX_CONCURRENT_PARSES")
    parse_timeout_seconds: int = Field(default=900, alias="PARSE_TIMEOUT_SECONDS")

    # Feature flags
    enable_chat: bool = Field(default=True, alias="ENABLE_CHAT")
    enable_diagrams: bool = Field(default=False, alias="ENABLE_DIAGRAMS")

    model_config = {"env_file": ".env", "populate_by_name": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
