from pathlib import Path as _Path

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

# Backend dir is the parent of this file's directory (backend/src/config.py → backend/).
_BACKEND_DIR = _Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent


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

    # Graph storage (LadybugDB)
    graph_db_path: str = Field(default="", alias="GRAPH_DB_PATH")

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")

    # LLM (Analysis/Chat)
    llm_provider: str = Field(default="lmstudio", alias="LLM_PROVIDER")
    llm_base_url: str = Field(default="http://localhost:1234/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="Qwen2.5-Coder-7B-Instruct", alias="LLM_MODEL")
    llm_api_key: str = Field(default="not-needed", alias="LLM_API_KEY")

    # Embeddings (Vector Indexing)
    embedding_base_url: str = Field(default="http://localhost:1234/v1", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="text-embedding-nomic-embed-text-v1.5", alias="EMBEDDING_MODEL")
    embedding_api_key: str = Field(default="not-needed", alias="EMBEDDING_API_KEY")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

    # Repository storage
    repo_cache_dir: str = Field(default="./cache/repos", alias="REPO_CACHE_DIR")

    # Data directory — root for all persistent artifacts (index cache, etc.).
    # Default resolves to {project_root}/cache.  Override via DATA_DIR env var.
    data_dir: str = Field(default="", alias="DATA_DIR")

    # When False, skip cache reads (still writes so cache is populated for next run).
    index_cache_enabled: bool = Field(default=True, alias="INDEX_CACHE_ENABLED")

    # Performance
    max_concurrent_parses: int = Field(default=5, alias="MAX_CONCURRENT_PARSES")
    parse_timeout_seconds: int = Field(default=900, alias="PARSE_TIMEOUT_SECONDS")
    wiki_agent_invoke_timeout_seconds: int = Field(
        default=0,
        alias="WIKI_AGENT_INVOKE_TIMEOUT_SECONDS",
    )
    wiki_agent_idle_timeout_seconds: int = Field(
        default=300,
        alias="WIKI_AGENT_IDLE_TIMEOUT_SECONDS",
    )
    wiki_agent_heartbeat_seconds: int = Field(
        default=15,
        alias="WIKI_AGENT_HEARTBEAT_SECONDS",
    )
    architect_context_max_chars: int = Field(
        default=32000,
        alias="ARCHITECT_CONTEXT_MAX_CHARS",
    )

    # Feature flags
    enable_chat: bool = Field(default=True, alias="ENABLE_CHAT")
    enable_diagrams: bool = Field(default=False, alias="ENABLE_DIAGRAMS")
    wiki_critic_enabled: bool = Field(default=True, alias="WIKI_CRITIC_ENABLED")
    wiki_auto_entity_linking_enabled: bool = Field(
        default=False,
        alias="WIKI_AUTO_ENTITY_LINKING_ENABLED",
    )
    wiki_quality_max_avg_sentence_words: int = Field(
        default=20,
        alias="WIKI_QUALITY_MAX_AVG_SENTENCE_WORDS",
    )
    wiki_quality_cross_page_similarity_threshold: float = Field(
        default=0.45,
        alias="WIKI_QUALITY_CROSS_PAGE_SIMILARITY_THRESHOLD",
    )

    model_config = {"env_file": ".env", "populate_by_name": True}

    @property
    def resolved_data_dir(self) -> str:
        """Absolute path to the data directory.

        If ``data_dir`` is empty (the default), resolves to
        ``{project_root}/cache``.  Otherwise treats ``data_dir`` as an
        absolute or backend-relative path.
        """
        if self.data_dir:
            p = _Path(self.data_dir)
            if not p.is_absolute():
                p = _BACKEND_DIR / p
            return str(p.resolve())
        return str(_PROJECT_ROOT / "cache")

    @property
    def resolved_graph_db_path(self) -> str:
        """Absolute path to LadybugDB graph file."""
        if self.graph_db_path:
            p = _Path(self.graph_db_path)
            if not p.is_absolute():
                p = _BACKEND_DIR / p
            return str(p.resolve())
        return str((_Path(self.resolved_data_dir) / "graph" / "code_graph.lbug").resolve())


@lru_cache
def get_settings() -> Settings:
    return Settings()
