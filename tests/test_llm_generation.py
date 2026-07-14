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
    assert LlmGenerationService().timeout_seconds == 180
    assert FakeAsyncClient.calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert FakeAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert "sk-test-secret" not in FakeAsyncClient.calls[0]["json"]["messages"][1]["content"]


def test_llm_timeout_error_includes_exception_type(monkeypatch):
    class TimingOutAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, headers, json):
            raise httpx.ReadTimeout("")

    monkeypatch.setattr(llm_generation.httpx, "AsyncClient", TimingOutAsyncClient)
    monkeypatch.setenv("APP_LLM_API_KEY", "sk-test-secret")

    with pytest.raises(llm_generation.LlmGenerationProviderError, match="ReadTimeout"):
        asyncio.run(
            LlmGenerationService().generate_text(
                system_prompt="s", prompt="p", provider="openai_compatible", model="gpt-test"
            )
        )


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


def test_anthropic_request_explicitly_enables_adaptive_thinking(monkeypatch):
    captured_payload = {}

    async def fake_post_json(**kwargs):
        captured_payload.update(kwargs["payload"])
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        return httpx.Response(
            200, request=request, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}
        )

    monkeypatch.setattr(llm_generation, "_post_json", fake_post_json)

    result = asyncio.run(
        llm_generation._post_anthropic_message(
            system_prompt="s",
            prompt="p",
            api_key="test",
            model="claude-sonnet-5",
            base_url="https://api.anthropic.com",
            timeout_seconds=1,
            max_tokens=100,
        )
    )

    assert result == "{}"
    assert captured_payload["thinking"] == {"type": "adaptive"}


def test_anthropic_empty_text_error_reports_stop_reason_and_block_types(monkeypatch):
    async def fake_post_json(**kwargs):
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        return httpx.Response(
            200, request=request, json={"stop_reason": "max_tokens", "content": [{"type": "thinking"}]}
        )

    monkeypatch.setattr(llm_generation, "_post_json", fake_post_json)

    with pytest.raises(
        llm_generation.LlmGenerationProviderError, match=r"stop_reason=max_tokens; content_types=thinking"
    ):
        asyncio.run(
            llm_generation._post_anthropic_message(
                system_prompt="s",
                prompt="p",
                api_key="test",
                model="claude-test",
                base_url="https://api.anthropic.com",
                timeout_seconds=1,
                max_tokens=100,
            )
        )
