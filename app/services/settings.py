from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_ITEMS_DIR = ROOT_DIR / "items"
DEFAULT_ENV_PATH = ROOT_DIR / ".env"
DEFAULT_LLM_PROVIDER = "openai_compatible"
DEFAULT_LLM_MODEL_BY_PROVIDER = {
    "openai_compatible": "gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
}
DEFAULT_LLM_BASE_URL_BY_PROVIDER = {
    "openai_compatible": "https://api.openai.com/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}
ANTHROPIC_MODEL_ALIASES = {
    "default": "claude-sonnet-5",
    "recommended": "claude-sonnet-5",
    "sonnet": "claude-sonnet-5",
    "sonnet 5": "claude-sonnet-5",
    "sonnet-5": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5-20251001",
    "haiku 4.5": "claude-haiku-4-5-20251001",
    "haiku-4.5": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-8",
    "opus 4.8": "claude-opus-4-8",
    "opus-4.8": "claude-opus-4-8",
}


class MissingLlmApiKeyError(RuntimeError):
    pass


class AppSettings(BaseSettings):
    """All APP_* configuration, sourced from environment and optional repo .env."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    data_dir: Path = DEFAULT_DATA_DIR
    items_dir: Path = DEFAULT_ITEMS_DIR
    log_level: str = "INFO"

    llm_provider: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""


def env_file_path() -> str | None:
    override = os.getenv("APP_ENV_FILE")
    if override is not None:
        return override or None
    return str(DEFAULT_ENV_PATH)


def get_app_settings() -> AppSettings:
    return AppSettings(_env_file=env_file_path())


@dataclass(frozen=True)
class WorkflowSettings:
    data_dir: Path = DEFAULT_DATA_DIR
    items_dir: Path = DEFAULT_ITEMS_DIR


def get_workflow_settings() -> WorkflowSettings:
    settings = get_app_settings()
    return WorkflowSettings(data_dir=settings.data_dir.expanduser(), items_dir=settings.items_dir.expanduser())


def get_llm_provider(request_provider: str | None = None, *, settings: AppSettings | None = None) -> str:
    if request_provider and request_provider.strip():
        return _normalize_provider_name(request_provider)
    settings = settings or get_app_settings()
    if settings.llm_provider.strip():
        return _normalize_provider_name(settings.llm_provider)
    detected = _detect_provider(settings)
    if detected:
        return detected
    return DEFAULT_LLM_PROVIDER


def get_llm_api_key(request_api_key: str | None = None, provider: str | None = None) -> str:
    if request_api_key and request_api_key.strip():
        return request_api_key.strip()
    settings = get_app_settings()
    resolved_provider = get_llm_provider(provider, settings=settings)
    candidates = _llm_api_key_candidates(settings, resolved_provider)
    for _, value in candidates:
        if value.strip():
            return value.strip()
    env_names = [name for name, _ in candidates]
    raise MissingLlmApiKeyError(
        f"Missing LLM API key. Set {env_names[0]} (or {', '.join(env_names[1:])}) in your .env file or pass api_key in the request."
    )


def get_llm_model(request_model: str | None = None, provider: str | None = None) -> str:
    settings = get_app_settings()
    resolved_provider = get_llm_provider(provider, settings=settings)
    if request_model and request_model.strip():
        return normalize_llm_model(request_model.strip(), provider=resolved_provider)
    if settings.llm_model.strip():
        return normalize_llm_model(settings.llm_model.strip(), provider=resolved_provider)
    return get_llm_default_model(resolved_provider)


def get_llm_default_model(provider: str | None = None) -> str:
    resolved_provider = get_llm_provider(provider)
    return DEFAULT_LLM_MODEL_BY_PROVIDER.get(resolved_provider, DEFAULT_LLM_MODEL_BY_PROVIDER[DEFAULT_LLM_PROVIDER])


def get_llm_base_url(request_base_url: str | None = None, provider: str | None = None) -> str:
    if request_base_url and request_base_url.strip():
        return request_base_url.strip()
    settings = get_app_settings()
    if settings.llm_base_url.strip():
        return settings.llm_base_url.strip()
    resolved_provider = get_llm_provider(provider, settings=settings)
    return DEFAULT_LLM_BASE_URL_BY_PROVIDER.get(resolved_provider, DEFAULT_LLM_BASE_URL_BY_PROVIDER[DEFAULT_LLM_PROVIDER])


def normalize_llm_model(model: str, provider: str | None = None) -> str:
    raw = str(model or "").strip()
    if not raw:
        return get_llm_default_model(provider)
    if get_llm_provider(provider) == "anthropic":
        alias_key = raw.lower().replace("·", " ").strip()
        return ANTHROPIC_MODEL_ALIASES.get(alias_key, raw)
    return raw


def _detect_provider(settings: AppSettings) -> str | None:
    api_key_candidates = [settings.llm_api_key, settings.openai_api_key, settings.anthropic_api_key]
    if any(key.strip().startswith("sk-ant") for key in api_key_candidates if key.strip()):
        return "anthropic"
    raw_model = settings.llm_model.strip().lower()
    if any(token in raw_model for token in ("claude", "sonnet", "haiku", "opus")):
        return "anthropic"
    return None


def _llm_api_key_candidates(settings: AppSettings, provider: str) -> list[tuple[str, str]]:
    generic = [("APP_LLM_API_KEY", settings.llm_api_key), ("APP_OPENAI_API_KEY", settings.openai_api_key)]
    anthropic = ("APP_ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if _normalize_provider_name(provider) == "anthropic":
        return [anthropic, *generic]
    return [*generic, anthropic]


def _normalize_provider_name(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")
