from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Protocol


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


class GeminiGateway(Protocol):
    model: str

    async def start(
        self,
        user_input: str,
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> ModelTurn: ...

    async def continue_with_results(
        self,
        previous_interaction_id: str,
        results: list[dict[str, Any]],
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> ModelTurn: ...


class GeminiRateLimitError(RuntimeError):
    """Raised after bounded retries cannot clear a provider rate limit."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("AI 免費額度暫時繁忙，請稍後再試。")
        self.retry_after_seconds = retry_after_seconds


class GeminiInteractionsGateway:
    """Thin adapter around Gemini's Interactions API.

    The SDK is imported lazily so the rest of the agent remains testable without
    network credentials or the provider package.
    """

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model = model

    async def start(
        self,
        user_input: str,
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        interaction = await self._create_with_retry(
            model=self.model,
            input=user_input,
            system_instruction=system_instruction,
            tools=tools,
        )
        return self._to_turn(interaction)

    async def continue_with_results(
        self,
        previous_interaction_id: str,
        results: list[dict[str, Any]],
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        interaction = await self._create_with_retry(
            model=self.model,
            previous_interaction_id=previous_interaction_id,
            input=results,
            system_instruction=system_instruction,
            tools=tools,
        )
        return self._to_turn(interaction)

    async def _create_with_retry(self, **kwargs: Any) -> Any:
        max_attempts = 3
        last_retry_after = 5.0
        for attempt in range(max_attempts):
            try:
                return await asyncio.to_thread(
                    self._client.interactions.create,
                    **kwargs,
                )
            except Exception as exc:
                retry_after = _rate_limit_retry_delay(exc, attempt)
                if retry_after is None:
                    raise
                last_retry_after = retry_after
                if attempt == max_attempts - 1:
                    raise GeminiRateLimitError(round(retry_after)) from exc
                await asyncio.sleep(retry_after)

        raise GeminiRateLimitError(round(last_retry_after))

    def _to_turn(self, interaction: Any) -> ModelTurn:
        calls = [
            FunctionCall(
                id=step.id,
                name=step.name,
                arguments=dict(step.arguments or {}),
            )
            for step in interaction.steps
            if step.type == "function_call"
        ]
        citations: list[SourceCitation] = []
        search_queries: list[str] = []
        for step in interaction.steps:
            if step.type == "google_search_call":
                arguments = getattr(step, "arguments", None) or {}
                queries = (
                    arguments.get("queries", [])
                    if isinstance(arguments, dict)
                    else getattr(arguments, "queries", [])
                )
                search_queries.extend(str(query) for query in queries)
            if step.type != "model_output":
                continue
            for block in getattr(step, "content", None) or []:
                block_text = getattr(block, "text", "") or ""
                for annotation in getattr(block, "annotations", None) or []:
                    if getattr(annotation, "type", None) != "url_citation":
                        continue
                    start = getattr(annotation, "start_index", None)
                    end = getattr(annotation, "end_index", None)
                    cited_text = None
                    if isinstance(start, int) and isinstance(end, int):
                        cited_text = block_text[start:end] or None
                    citations.append(
                        SourceCitation(
                            title=getattr(annotation, "title", None) or "來源",
                            url=getattr(annotation, "url", ""),
                            cited_text=cited_text,
                        )
                    )
        return ModelTurn(
            id=interaction.id,
            output_text=interaction.output_text or "",
            function_calls=calls,
            citations=_deduplicate_citations(citations),
            search_queries=list(dict.fromkeys(search_queries)),
        )


def _deduplicate_citations(citations: list[SourceCitation]) -> list[SourceCitation]:
    unique: dict[str, SourceCitation] = {}
    for citation in citations:
        if citation.url:
            unique.setdefault(citation.url, citation)
    return list(unique.values())


def _rate_limit_retry_delay(exc: Exception, attempt: int) -> float | None:
    message = str(exc)
    normalized = message.lower()
    rate_limited = any(
        marker in normalized
        for marker in ("429", "quota exceeded", "rate limit", "too_many_requests")
    )
    if not rate_limited:
        return None

    match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, re.IGNORECASE)
    if match:
        # A small buffer avoids retrying in the same rolling quota window.
        return min(max(float(match.group(1)) + 0.75, 1.0), 45.0)
    return min(5.0 * (2**attempt), 30.0)
