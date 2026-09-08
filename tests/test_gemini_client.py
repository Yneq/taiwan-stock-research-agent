from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.clients.gemini as gemini_module
from app.clients.gemini import GeminiInteractionsGateway, GeminiRateLimitError


class FakeInteractions:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(
                "Error code: 429 - quota exceeded; please retry in 0.25s"
            )
        return SimpleNamespace(id="interaction-1", steps=[], output_text="研究完成")


def build_gateway(interactions: FakeInteractions) -> GeminiInteractionsGateway:
    gateway = GeminiInteractionsGateway.__new__(GeminiInteractionsGateway)
    gateway._client = SimpleNamespace(interactions=interactions)
    gateway.model = "test-model"
    return gateway


@pytest.mark.asyncio
async def test_long_rate_limit_returns_without_sleeping(monkeypatch):
    interactions = FakeInteractions(0)
    def fail(**kwargs):
        raise RuntimeError("429 retry in 40s")
    interactions.create = fail
    async def unexpected_sleep(seconds):
        raise AssertionError("Long cooldown must not keep user waiting")
    monkeypatch.setattr(gemini_module.asyncio, "sleep", unexpected_sleep)
    with pytest.raises(GeminiRateLimitError):
        await build_gateway(interactions).start("問題", "規則", [])


@pytest.mark.asyncio
async def test_retries_provider_rate_limit_then_returns_answer(monkeypatch) -> None:
    interactions = FakeInteractions(failures=1)
    gateway = build_gateway(interactions)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(gemini_module.asyncio, "sleep", fake_sleep)

    turn = await gateway.start("問題", "規則", [])

    assert turn.output_text == "研究完成"
    assert interactions.calls == 2
    assert sleep_calls == [1.0]


@pytest.mark.asyncio
async def test_raises_normalized_rate_limit_after_bounded_retries(monkeypatch) -> None:
    interactions = FakeInteractions(failures=3)
    gateway = build_gateway(interactions)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(gemini_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(GeminiRateLimitError) as exc:
        await gateway.start("問題", "規則", [])

    assert exc.value.retry_after_seconds == 1
    assert interactions.calls == 3
    assert sleep_calls == [1.0, 1.0]


@pytest.mark.asyncio
async def test_does_not_retry_unrelated_provider_error(monkeypatch) -> None:
    interactions = FakeInteractions(failures=0)
    gateway = build_gateway(interactions)

    def fail_without_rate_limit(**kwargs: object) -> SimpleNamespace:
        raise RuntimeError("invalid API key")

    interactions.create = fail_without_rate_limit  # type: ignore[method-assign]

    async def fail_if_called(seconds: float) -> None:
        raise AssertionError("sleep should not be called")

    monkeypatch.setattr(gemini_module.asyncio, "sleep", fail_if_called)

    with pytest.raises(RuntimeError, match="invalid API key"):
        await gateway.start("問題", "規則", [])
