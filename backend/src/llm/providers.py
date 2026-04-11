from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from threading import Lock

from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedLLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float
    retryable_statuses: frozenset[int]
    provider: str


# Maps Settings field name → env var alias used to detect explicit overrides.
_FIELD_ENV_VARS = {
    "llm_base_url": "LLM_BASE_URL",
    "llm_model": "LLM_MODEL",
    "llm_api_key": "LLM_API_KEY",
}

_PROVIDER_PRESETS = {
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "model": "Qwen2.5-Coder-7B-Instruct",
        "timeout": 300.0,
        "retryable_statuses": frozenset(range(100, 600)),
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "timeout": 120.0,
        "retryable_statuses": frozenset({429, 500, 502, 503, 504}),
    },
    "github": {
        "base_url": "https://models.github.ai/inference",
        "model": "openai/gpt-4.1-mini",
        "timeout": 120.0,
        "retryable_statuses": frozenset({429, 500, 502, 503, 504}),
    },
}

_resolved_config_cache: dict[tuple[str, str, str, str, str, str], ResolvedLLMConfig] = {}
_cache_lock = Lock()


def _is_explicitly_set(field_name: str) -> bool:
    """True when the user set the corresponding env var (presence-based, not value-based)."""
    env_var = _FIELD_ENV_VARS.get(field_name)
    return env_var is not None and env_var in os.environ


def _resolve_github_token(settings: Settings) -> str:
    if _is_explicitly_set("llm_api_key"):
        return settings.llm_api_key

    env_token = os.getenv("GITHUB_TOKEN")
    if env_token:
        return env_token

    if settings.app_env != "production":
        try:
            result = subprocess.run(  # noqa: S603
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            token = result.stdout.strip()
            if result.returncode == 0 and token:
                return token
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unable to read GitHub CLI token: %s", exc)

    raise ValueError("GitHub Models requires a token. Set GITHUB_TOKEN or LLM_API_KEY env var.")


def validate_embeddings_config(settings: Settings) -> None:
    if settings.llm_provider == "github" and settings.embedding_base_url.startswith("http://localhost"):
        logger.warning(
            "GitHub Models does not provide embeddings. Embedding config still points to localhost — "
            "ensure a local embedding server is running."
        )


def resolve_provider(settings: Settings) -> ResolvedLLMConfig:
    provider = settings.llm_provider.lower()
    preset = _PROVIDER_PRESETS.get(provider)
    if preset is None:
        raise ValueError(f"Unsupported llm_provider: {settings.llm_provider}")

    github_token = _resolve_github_token(settings) if provider == "github" else ""
    cache_key = (
        provider,
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.app_env,
        github_token,
    )

    with _cache_lock:
        cached = _resolved_config_cache.get(cache_key)
        if cached is not None:
            return cached

        base_url = (
            settings.llm_base_url
            if _is_explicitly_set("llm_base_url")
            else preset["base_url"]
        )
        model = settings.llm_model if _is_explicitly_set("llm_model") else preset["model"]
        if provider == "github":
            api_key = github_token
        else:
            api_key = settings.llm_api_key if _is_explicitly_set("llm_api_key") else preset.get("api_key", "not-needed")

        validate_embeddings_config(settings)

        resolved = ResolvedLLMConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=float(preset["timeout"]),
            retryable_statuses=preset["retryable_statuses"],
            provider=provider,
        )
        _resolved_config_cache[cache_key] = resolved
        return resolved
