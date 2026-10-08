from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.progress import emit, measured, stage


@dataclass(frozen=True, slots=True)
class FunctionCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SourceCitation:
    title: str
    url: str
    cited_text: str | None = None


@dataclass(frozen=True, slots=True)
class ModelTurn:
    id: str
    output_text: str
    function_calls: list[FunctionCall]
    citations: list[SourceCitation]
    search_queries: list[str]
    model: str | None = None


class GeminiGateway(Protocol):
    model: str

    async def start(
        self,
        user_input: str,
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> ModelTurn: ...


class GeminiRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("AI 模型免費額度已用完，備用模型也暫時無法使用。")
        self.retry_after_seconds = retry_after_seconds


class GeminiServiceError(RuntimeError):
    """Provider failure without exposing response bodies or credentials."""


class GeminiSynthesisGateway:
    """Single-pass Gemini synthesis with an immediate lower-cost model fallback.

    The old Interactions SDK hid quota errors behind long retries. No model
    tools are enabled now, so the supported generateContent HTTP endpoint gives
    us explicit 429 handling and a real per-request deadline.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str = "gemini-3.5-flash-lite",
        timeout_seconds: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.fallback_model = fallback_model
        self._primary_unavailable_until = 0.0
        self._fallback_timeout_seconds = 30.0
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com",
            timeout=httpx.Timeout(timeout_seconds),
            headers={"x-goog-api-key": api_key},
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @measured("Gemini 單次整合（含備用模型）")
    async def start(
        self,
        user_input: str,
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        if tools:
            raise ValueError("Synthesis must not expose tools to Gemini")

        if self.fallback_model != self.model and time.monotonic() < self._primary_unavailable_until:
            emit(stage="Gemini 備用模型", status="retry", reason="primary_quota_cooldown")
            return await self._generate(self.fallback_model, user_input, system_instruction)

        try:
            return await self._generate(self.model, user_input, system_instruction)
        except (GeminiRateLimitError, GeminiServiceError, TimeoutError) as exc:
            if isinstance(exc, GeminiRateLimitError):
                self._primary_unavailable_until = time.monotonic() + exc.retry_after_seconds
            elif isinstance(exc, TimeoutError):
                self._primary_unavailable_until = time.monotonic() + 60
            if self.fallback_model == self.model:
                raise
            emit(stage="Gemini 備用模型", status="retry", reason=type(exc).__name__)
            async with stage("Gemini 備用模型"):
                return await self._generate(
                    self.fallback_model, user_input, system_instruction
                )

    async def _generate(
        self, model: str, user_input: str, system_instruction: str
    ) -> ModelTurn:
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_input}]}],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": "low"},
                "maxOutputTokens": 1200,
            },
        }
        try:
            response = await self._client.post(
                f"/v1beta/models/{model}:generateContent", json=payload,
                **({"timeout": self._fallback_timeout_seconds}
                   if model == self.fallback_model and model != self.model else {}),
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Gemini request timed out") from exc
        except httpx.RequestError as exc:
            raise GeminiServiceError("Gemini 連線失敗") from exc

        if response.status_code == 429:
            raise GeminiRateLimitError(_retry_after_seconds(response))
        if response.status_code >= 500:
            raise GeminiServiceError("Gemini 服務暫時無法使用")
        if not response.is_success:
            raise GeminiServiceError(f"Gemini 設定或請求錯誤（HTTP {response.status_code}）")

        try:
            data = response.json()
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            output = "".join(
                part.get("text", "") for part in parts if not part.get("thought")
            ).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise GeminiServiceError("Gemini 回應格式不正確") from exc
        if not output:
            raise GeminiServiceError("Gemini 未產生可用回答")

        return ModelTurn(
            id=str(data.get("responseId", "")),
            output_text=output,
            function_calls=[],
            citations=[],
            search_queries=[],
            model=model,
        )


def _retry_after_seconds(response: httpx.Response) -> int:
    header = response.headers.get("Retry-After", "")
    if header.isdigit():
        return min(int(header), 24 * 60 * 60)
    try:
        message = str(response.json().get("error", {}).get("message", ""))
    except (ValueError, AttributeError):
        return 60
    match = re.search(r"Please retry in\s+(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", message)
    if match:
        return min(
            round(int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + float(match.group(3))),
            24 * 60 * 60,
        )
    return 60
