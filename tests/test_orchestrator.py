from __future__ import annotations

from collections import deque

import pytest

from app.agent.orchestrator import AgentIncompleteError, ResearchOrchestrator
from app.clients.gemini import FunctionCall, ModelTurn, SourceCitation
from app.tools.executor import ToolExecution


class FakeGateway:
    model = "test-model"

    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = deque(turns)
        self.continuations: list[list[dict]] = []

    async def start(
        self, user_input: str, system_instruction: str, tools: list[dict]
    ) -> ModelTurn:
        assert "不提供買賣建議" in system_instruction
        assert user_input
        assert any(tool.get("name") == "get_stock_snapshot" for tool in tools)
        assert any(tool.get("name") == "search_news" for tool in tools)
        return self.turns.popleft()

    async def continue_with_results(
        self,
        previous_interaction_id: str,
        results: list[dict],
        system_instruction: str,
        tools: list[dict],
    ) -> ModelTurn:
        assert "禁止自行推測" in system_instruction
        self.continuations.append(results)
        return self.turns.popleft()


class FakeExecutor:
    async def execute(self, call_id: str, name: str, arguments: dict) -> ToolExecution:
        if name == "search_news":
            result = {
                "query": arguments["query"],
                "articles": [
                    {
                        "title": "台積電近期消息",
                        "url": "https://example.com/news",
                        "source": "範例新聞",
                        "publishedAt": "2026-08-05T08:00:00+00:00",
                    }
                ],
            }
        else:
            result = {
                "stockCode": "2330",
                "currentPrice": 1120,
                "changePercent": 1.36,
            }
        return ToolExecution(
            call_id=call_id,
            name=name,
            arguments=arguments,
            result=result,
            status="success",
            duration_ms=12,
        )


def turn(
    identifier: str,
    *,
    text: str = "",
    calls: list[FunctionCall] | None = None,
    citations: list[SourceCitation] | None = None,
    queries: list[str] | None = None,
) -> ModelTurn:
    return ModelTurn(
        id=identifier,
        output_text=text,
        function_calls=calls or [],
        citations=citations or [],
        search_queries=queries or [],
    )


@pytest.mark.asyncio
async def test_executes_tool_and_returns_grounded_answer() -> None:
    gateway = FakeGateway(
        [
            turn(
                "turn-1",
                calls=[
                    FunctionCall(
                        "call-1", "get_stock_snapshot", {"stock_code": "2330"}
                    ),
                    FunctionCall(
                        "call-2",
                        "search_news",
                        {"query": "台積電 近期新聞", "days": 7},
                    ),
                ],
            ),
            turn(
                "turn-2",
                text="摘要\n台積電目前成交價為 1120 元。",
            ),
        ]
    )
    orchestrator = ResearchOrchestrator(gateway, FakeExecutor(), max_steps=3)

    outcome = await orchestrator.research("台積電今天股價如何？")

    assert "1120" in outcome.answer
    assert [trace.tool for trace in outcome.traces] == [
        "get_stock_snapshot",
        "search_news",
    ]
    assert outcome.traces[0].data == {
        "stockCode": "2330",
        "currentPrice": 1120,
        "changePercent": 1.36,
    }
    assert outcome.traces[1].data is None
    assert outcome.citations[0].url == "https://example.com/news"
    assert gateway.continuations[0][0]["type"] == "function_result"


@pytest.mark.asyncio
async def test_returns_direct_answer_without_unnecessary_stock_tool() -> None:
    gateway = FakeGateway([turn("turn-1", text="本系統不提供買賣建議。")])
    orchestrator = ResearchOrchestrator(gateway, FakeExecutor())

    outcome = await orchestrator.research("你可以直接告訴我該買哪一檔嗎？")

    assert outcome.traces == []
    assert "不提供買賣建議" in outcome.answer


@pytest.mark.asyncio
async def test_stops_repeated_tool_loop() -> None:
    repeated = [
        turn(
            f"turn-{index}",
            calls=[FunctionCall(f"call-{index}", "get_stock_snapshot", {"stock_code": "2330"})],
        )
        for index in range(1, 4)
    ]
    gateway = FakeGateway(repeated)
    orchestrator = ResearchOrchestrator(gateway, FakeExecutor(), max_steps=2)

    with pytest.raises(AgentIncompleteError, match="工具呼叫上限"):
        await orchestrator.research("一直查詢")
