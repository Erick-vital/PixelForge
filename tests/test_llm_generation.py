from __future__ import annotations

import asyncio
from typing import ClassVar

import httpx
import pytest

from app.services import llm_generation
from app.services.llm_generation import LlmGenerationService
from app.services.settings import MissingLlmApiKeyError, get_llm_model


class FakeAsyncClient:
    calls: ClassVar[list[dict]] = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, headers, json):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json})
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"choices": [{"message": {"content": "generated text"}}]})


def test_llm_service_uses_openai_compatible_provider_without_leaking_secret(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("APP_LLM_API_KEY", "sk-test-secret")

    result = asyncio.run(
        LlmGenerationService().generate_text(
            system_prompt="You are concise.",
            prompt="Say hi",
            provider="openai_compatible",
            model="gpt-test",
        )
    )

    assert result.text == "generated text"
    assert result.provider == "openai_compatible"
    assert result.model == "gpt-test"
    assert FakeAsyncClient.calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert FakeAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert "sk-test-secret" not in FakeAsyncClient.calls[0]["json"]["messages"][1]["content"]


def test_missing_llm_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("APP_LLM_API_KEY", raising=False)
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("APP_ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(MissingLlmApiKeyError, match="Missing LLM API key"):
        asyncio.run(LlmGenerationService().generate_text(system_prompt="s", prompt="p"))


def test_anthropic_model_aliases(monkeypatch):
    monkeypatch.setenv("APP_LLM_PROVIDER", "anthropic")
    assert get_llm_model("Sonnet", provider="anthropic") == "claude-sonnet-5"
    assert get_llm_model("Haiku", provider="anthropic") == "claude-haiku-4-5-20251001"
