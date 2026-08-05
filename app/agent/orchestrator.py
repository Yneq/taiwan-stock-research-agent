from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.clients.gemini import GeminiGateway, SourceCitation
from app.schemas.research import Citation, ToolTrace
from app.tools.definitions import build_tools
from app.tools.executor import ToolExecution, ToolExecutor


SYSTEM_PROMPT = """
你是台灣股票研究助理，只整理公開資訊，不預測股價、不提供買賣建議。

規則：
1. 回答即時價格、開盤、昨收或漲跌幅前，必須呼叫 get_stock_snapshot。
2. 只有使用者詢問營收或基本面趨勢時，才呼叫 get_revenue_history。
3. 解釋近期事件時呼叫 search_news，優先採用公司公告、交易所與可信新聞來源。
4. 數字必須忠實使用工具結果，禁止自行推測或修改。
5. 區分已確認事實與可能影響因素，不把時間相關性寫成直接因果。
6. 若資料不足或工具失敗，清楚說明限制，不得編造答案。
7. 最終使用繁體中文，包含「摘要、關鍵數據、可能影響因素、資料限制」四部分。
""".strip()


class AgentIncompleteError(RuntimeError):
    """Raised when the agent reaches its bounded tool-call limit."""


@dataclass(frozen=True, slots=True)
class ResearchOutcome:
    answer: str
    traces: list[ToolTrace]
    citations: list[Citation]


class ResearchOrchestrator:
    def __init__(
        self,
        gateway: GeminiGateway,
        executor: ToolExecutor,
        max_steps: int = 3,
    ) -> None:
        self._gateway = gateway
        self._executor = executor
        self._max_steps = max_steps
        self._tools = build_tools()

    @property
    def model(self) -> str:
        return self._gateway.model

    async def research(self, question: str) -> ResearchOutcome:
        turn = await self._gateway.start(
            user_input=question,
            system_instruction=SYSTEM_PROMPT,
            tools=self._tools,
        )
        traces: list[ToolTrace] = []
        citations: list[SourceCitation] = []

        for _ in range(self._max_steps):
            citations.extend(turn.citations)
            if turn.search_queries:
                traces.append(
                    ToolTrace(
                        tool="google_search",
                        arguments={"queries": turn.search_queries},
                        status="success",
                        duration_ms=0,
                    )
                )
            if not turn.function_calls:
                if not turn.output_text.strip():
                    raise AgentIncompleteError("模型沒有產生可用回答")
                return ResearchOutcome(
                    answer=turn.output_text,
                    traces=traces,
                    citations=self._to_api_citations(citations),
                )

            executions = await asyncio.gather(
                *(
                    self._executor.execute(call.id, call.name, call.arguments)
                    for call in turn.function_calls
                )
            )
            traces.extend(
                ToolTrace(
                    tool=item.name,
                    arguments=item.arguments,
                    status=item.status,
                    duration_ms=item.duration_ms,
                    error=item.error,
                )
                for item in executions
            )
            citations.extend(self._citations_from_tool_results(executions))
            turn = await self._gateway.continue_with_results(
                previous_interaction_id=turn.id,
                results=[item.as_function_result() for item in executions],
                system_instruction=SYSTEM_PROMPT,
                tools=self._tools,
            )

        if turn.output_text.strip() and not turn.function_calls:
            citations.extend(turn.citations)
            return ResearchOutcome(
                answer=turn.output_text,
                traces=traces,
                citations=self._to_api_citations(citations),
            )
        raise AgentIncompleteError("Agent 已達工具呼叫上限，無法安全完成回答")

    def _citations_from_tool_results(
        self, executions: list[ToolExecution]
    ) -> list[SourceCitation]:
        citations: list[SourceCitation] = []
        for execution in executions:
            if execution.name != "search_news" or execution.status != "success":
                continue
            for article in execution.result.get("articles", []):
                url = article.get("url", "")
                if not url:
                    continue
                citations.append(
                    SourceCitation(
                        title=article.get("title") or article.get("source") or "新聞來源",
                        url=url,
                        cited_text=article.get("title") or None,
                    )
                )
        return citations

    def _to_api_citations(self, citations: list[SourceCitation]) -> list[Citation]:
        unique: dict[str, Citation] = {}
        for citation in citations:
            if citation.url:
                unique.setdefault(
                    citation.url,
                    Citation(
                        title=citation.title,
                        url=citation.url,
                        cited_text=citation.cited_text,
                    ),
                )
        return list(unique.values())
