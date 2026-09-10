from __future__ import annotations

import asyncio
from collections import deque

import pytest

from app.agent.orchestrator import ResearchOrchestrator
from app.clients.gemini import FunctionCall, ModelTurn, SourceCitation
from app.tools.executor import ToolExecution


class FakeGateway:
    model = "test-model"

    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = deque(turns)
        self.starts: list[tuple[str, list[dict]]] = []

    async def start(
        self, user_input: str, system_instruction: str, tools: list[dict]
    ) -> ModelTurn:
        assert "不提供買賣建議" in system_instruction
        assert user_input
        assert tools == []
        self.starts.append((user_input, tools))
        return self.turns.popleft()

    async def continue_with_results(
        self,
        previous_interaction_id: str,
        results: list[dict],
        system_instruction: str,
        tools: list[dict],
    ) -> ModelTurn:
        raise AssertionError("One-pass research must not continue a Gemini turn")


class GatewayMustNotRun:
    model = "test-model"

    async def start(self, *args, **kwargs):
        raise AssertionError("Simple quote must bypass Gemini")


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, call_id: str, name: str, arguments: dict) -> ToolExecution:
        self.calls.append((name, arguments))
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
        elif name == "get_revenue_history":
            result = {
                "stockCode": arguments["stock_code"],
                "months": arguments.get("months", 12),
                "items": [{"yearMonth": "2026-07", "revenue": 100}],
            }
        else:
            result = {
                "stockCode": arguments["stock_code"],
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


class FailingExecutor:
    async def execute(self, call_id: str, name: str, arguments: dict) -> ToolExecution:
        return ToolExecution(
            call_id=call_id,
            name=name,
            arguments=arguments,
            result={"error": "FinMind token is unavailable"},
            status="error",
            duration_ms=8,
            error="FinMind token is unavailable",
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
async def test_simple_quote_with_code_bypasses_gemini() -> None:
    orchestrator = ResearchOrchestrator(GatewayMustNotRun(), FakeExecutor())

    outcome = await orchestrator.research("聯發科 2454 今天股價如何？相較昨收漲跌多少？")

    assert orchestrator.model_for("2454股價") == "StockTracker · deterministic"
    assert len(outcome.traces) == 1
    assert outcome.traces[0].tool == "get_stock_snapshot"
    assert "1120" in outcome.answer
    assert "未額外搜尋新聞" in outcome.answer


@pytest.mark.asyncio
async def test_news_question_still_uses_gemini() -> None:
    gateway = FakeGateway([turn("turn-1", text="近期新聞摘要")])
    executor = FakeExecutor()
    orchestrator = ResearchOrchestrator(gateway, executor)

    outcome = await orchestrator.research("台積電 2330 今天股價為什麼上漲？有哪些新聞？")

    assert orchestrator.model_for("台積電 2330 今天股價為什麼上漲？有哪些新聞？") == "test-model"
    assert outcome.answer == "近期新聞摘要"
    assert [name for name, _ in executor.calls] == ["get_stock_snapshot", "search_news"]
    assert len(gateway.starts) == 1
    assert outcome.citations[0].url == "https://example.com/news"


@pytest.mark.asyncio
async def test_full_research_prefetches_all_data_before_one_gemini_call() -> None:
    gateway = FakeGateway([turn("turn-1", text="摘要\n已完成完整研究。")])
    executor = FakeExecutor()
    orchestrator = ResearchOrchestrator(gateway, executor)

    outcome = await orchestrator.research(
        "整理台積電 2330 今天的股價、最近三個月營收與近期重要新聞。"
    )

    assert [trace.tool for trace in outcome.traces] == [
        "get_stock_snapshot",
        "get_revenue_history",
        "search_news",
    ]
    assert executor.calls[1][1]["months"] == 3
    assert len(gateway.starts) == 1
    synthesis_input, tools = gateway.starts[0]
    assert tools == []
    assert '"get_stock_snapshot"' in synthesis_input
    assert '"get_revenue_history"' in synthesis_input
    assert '"search_news"' in synthesis_input
    assert outcome.citations[0].url == "https://example.com/news"


@pytest.mark.asyncio
async def test_returns_direct_answer_without_unnecessary_stock_tool() -> None:
    gateway = FakeGateway([turn("turn-1", text="本系統不提供買賣建議。")])
    executor = FakeExecutor()
    orchestrator = ResearchOrchestrator(gateway, executor)

    outcome = await orchestrator.research("你可以直接告訴我該買哪一檔嗎？")

    assert outcome.traces == []
    assert executor.calls == []
    assert len(gateway.starts) == 1
    assert "不提供買賣建議" in outcome.answer


@pytest.mark.asyncio
async def test_tool_failure_forces_a_final_limitation_answer() -> None:
    gateway = FakeGateway([turn("turn-1", text="資料限制\nFinMind 暫時無法取得月營收資料。")])
    orchestrator = ResearchOrchestrator(gateway, FailingExecutor(), max_steps=3)

    outcome = await orchestrator.research("台積電 2330 最近月營收如何？")

    assert outcome.traces[0].status == "error"
    assert "FinMind" in outcome.answer
    assert "FinMind token is unavailable" in gateway.starts[0][0]
    assert len(gateway.starts) == 1


@pytest.mark.asyncio
async def test_comparison_fetches_both_quotes_before_one_gemini_call() -> None:
    gateway = FakeGateway([turn("turn-1", text="比較完成")])
    executor = FakeExecutor()
    orchestrator = ResearchOrchestrator(gateway, executor)

    outcome = await orchestrator.research("比較 2330 與 2454 今天的股價表現")

    assert [trace.arguments["stock_code"] for trace in outcome.traces] == ["2330", "2454"]
    assert len(gateway.starts) == 1


@pytest.mark.asyncio
async def test_planned_tools_run_concurrently() -> None:
    class ConcurrentExecutor(FakeExecutor):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        async def execute(self, call_id: str, name: str, arguments: dict) -> ToolExecution:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0)
            try:
                return await super().execute(call_id, name, arguments)
            finally:
                self.active -= 1

    gateway = FakeGateway([turn("turn-1", text="完成")])
    executor = ConcurrentExecutor()
    orchestrator = ResearchOrchestrator(gateway, executor)

    await orchestrator.research("整理台積電 2330 股價、營收與新聞")

    assert executor.max_active == 3


@pytest.mark.parametrize("question,tool,code", [
    ("聯發科今天相較昨收漲跌多少？", "get_stock_snapshot", "2454"),
    ("台積電最近六個月營收", "get_revenue_history", "2330"),
])
def test_known_company_name_keeps_data_retrieval(question, tool, code):
    calls = ResearchOrchestrator._plan_research(question)
    assert any(name == tool and args["stock_code"] == code for _, name, args in calls)


@pytest.mark.asyncio
async def test_quote_and_messages_does_not_skip_news():
    gateway = FakeGateway([turn("one", text="行情與消息")])
    executor = FakeExecutor()
    orchestrator = ResearchOrchestrator(gateway, executor)
    outcome = await orchestrator.research("2454 今天股價和重要消息")
    assert [trace.tool for trace in outcome.traces] == ["get_stock_snapshot", "search_news"]
    assert len(gateway.starts) == 1


@pytest.mark.parametrize('question,query,fallback', [
    ('台積電最近一週有哪些可能影響公司的重要新聞？', '台積電', None),
    ('聯發科 2454 最近有哪些 AI 晶片相關的重要消息？', '聯發科 AI 晶片', '聯發科'),
    ('鴻海最近有哪些電動車相關的重要消息？', '鴻海 電動車', '鴻海'),
    ('整理台積電 2330 今天的股價、最近月營收與近期重要新聞。', '台積電', None),
])
def test_news_button_keywords(question, query, fallback):
    args = next(args for _, name, args in ResearchOrchestrator._plan_research(question) if name == 'search_news')
    assert args['query'] == query
    assert args['fallback_query'] == fallback
