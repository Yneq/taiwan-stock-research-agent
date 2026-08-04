from __future__ import annotations

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
        import asyncio

        interaction = await asyncio.to_thread(
            self._client.interactions.create,
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
        import asyncio

        interaction = await asyncio.to_thread(
            self._client.interactions.create,
            model=self.model,
            previous_interaction_id=previous_interaction_id,
            input=results,
            system_instruction=system_instruction,
            tools=tools,
        )
        return self._to_turn(interaction)

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
