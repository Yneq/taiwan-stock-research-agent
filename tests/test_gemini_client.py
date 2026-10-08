from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.clients.gemini import (
    GeminiSynthesisGateway,
    GeminiRateLimitError,
    GeminiServiceError,
)


def success(text: str = "研究完成") -> httpx.Response:
    return httpx.Response(200, json={
        "responseId": "response-1",
        "candidates": [{"content": {"parts": [{"text": text}]}}],
    })


def gateway(handler, *, model: str = "gemini-3.6-flash") -> GeminiSynthesisGateway:
    client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    return GeminiSynthesisGateway("test-key", model, client=client)


@pytest.mark.asyncio
async def test_primary_model_synthesizes_without_tools() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return success()

    turn = await gateway(handler).start("問題", "規則", [])

    assert turn.output_text == "研究完成"
    assert turn.model == "gemini-3.6-flash"
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/gemini-3.6-flash:generateContent")
    body = json.loads(requests[0].content)
    assert body["systemInstruction"]["parts"][0]["text"] == "規則"
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"


@pytest.mark.asyncio
async def test_primary_daily_quota_switches_to_lite_and_skips_primary_afterward() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "3.6-flash" in request.url.path:
            return httpx.Response(429, json={"error": {
                "message": "Quota exceeded. Please retry in 8h7m1.6s."
            }})
        return success("備用模型完成")

    client = gateway(handler)
    first = await client.start("問題", "規則", [])
    second = await client.start("另一個問題", "規則", [])

    assert first.model == second.model == "gemini-3.5-flash-lite"
    assert first.output_text == "備用模型完成"
    assert len(calls) == 3
    assert "3.6-flash" in calls[0]
    assert "flash-lite" in calls[1]
    assert "flash-lite" in calls[2]


@pytest.mark.asyncio
async def test_both_models_rate_limited_returns_clear_error() -> None:
    client = gateway(lambda request: httpx.Response(429, json={
        "error": {"message": "Quota exceeded. Please retry in 60s."}
    }))

    with pytest.raises(GeminiRateLimitError) as exc:
        await client.start("問題", "規則", [])

    assert exc.value.retry_after_seconds == 60


@pytest.mark.asyncio
async def test_non_rate_limit_provider_error_is_not_reported_as_quota() -> None:
    client = gateway(lambda request: httpx.Response(400, json={
        "error": {"message": "Invalid API key"}
    }))

    with pytest.raises(GeminiServiceError, match="HTTP 400"):
        await client.start("問題", "規則", [])


@pytest.mark.asyncio
async def test_provider_timeout_tries_backup_once() -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "3.6-flash" in request.url.path:
            raise httpx.ReadTimeout("provider stalled")
        return success("備用模型完成")

    turn = await gateway(handler).start("問題", "規則", [])

    assert turn.model == "gemini-3.5-flash-lite"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_tools_are_rejected_before_provider_call() -> None:
    client = gateway(lambda request: success())
    with pytest.raises(ValueError, match="must not expose tools"):
        await client.start("問題", "規則", [{"name": "unsafe"}])
