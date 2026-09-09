from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from app.clients.gemini import GeminiGateway, SourceCitation
from app.schemas.research import Citation, ToolTrace
from app.tools.definitions import build_tools
from app.tools.executor import ToolExecution, ToolExecutor
from app.progress import stage


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
8. 公司名稱與股票代碼不得自行猜測；有工具結果時以 stockCode 與 stockName 為準，未核對時不要補上使用者未提供的代碼。
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
        stock_code = self._simple_quote_code(question)
        if stock_code:
            async with stage("純行情快速路徑"):
                execution = await self._executor.execute(
                    "fast-quote", "get_stock_snapshot", {"stock_code": stock_code}
                )
            trace = ToolTrace(
                tool=execution.name,
                arguments=execution.arguments,
                status=execution.status,
                duration_ms=execution.duration_ms,
                error=execution.error,
                data=execution.result if execution.status == "success" else None,
            )
            if execution.status == "success":
                return ResearchOutcome(
                    answer=self._quote_answer(execution.result),
                    traces=[trace],
                    citations=[],
                )
            return ResearchOutcome(
                answer=self._bounded_fallback_answer([trace]),
                traces=[trace],
                citations=[],
            )

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
                    data=(
                        item.result
                        if item.status == "success"
                        and item.name
                        in {"get_stock_snapshot", "get_revenue_history"}
                        else None
                    ),
                )
                for item in executions
            )
            citations.extend(self._citations_from_tool_results(executions))
            # A failed data source is already a complete, meaningful result.
            # Remove tools for the next turn so the model must explain the
            # limitation instead of repeatedly calling the same broken tool
            # until the bounded agent loop becomes an HTTP 502.
            next_tools = (
                []
                if any(item.status != "success" for item in executions)
                else self._tools
            )
            turn = await self._gateway.continue_with_results(
                previous_interaction_id=turn.id,
                results=[item.as_function_result() for item in executions],
                system_instruction=SYSTEM_PROMPT,
                tools=next_tools,
            )

        if turn.output_text.strip() and not turn.function_calls:
            citations.extend(turn.citations)
            return ResearchOutcome(
                answer=turn.output_text,
                traces=traces,
                citations=self._to_api_citations(citations),
            )
        citations.extend(turn.citations)
        return ResearchOutcome(
            answer=self._bounded_fallback_answer(traces),
            traces=traces,
            citations=self._to_api_citations(citations),
        )

    @staticmethod
    def _simple_quote_code(question: str) -> str | None:
        codes = re.findall(r"(?<!\d)(\d{4})(?!\d)", question)
        if len(set(codes)) != 1:
            return None
        quote_terms = ("股價", "成交價", "行情", "漲跌", "昨收", "開盤", "今天", "今日", "現在", "目前")
        research_terms = ("新聞", "事件", "營收", "基本面", "比較", "為什麼", "原因", "展望", "趨勢", "完整研究")
        if not any(term in question for term in quote_terms):
            return None
        if any(term in question for term in research_terms):
            return None
        return codes[0]

    @staticmethod
    def _quote_answer(data: dict) -> str:
        def value(name: str, fallback="—"):
            result = data.get(name)
            return fallback if result is None or result == "" else result

        change = data.get("change")
        percent = data.get("changePercent")
        direction = "上漲" if isinstance(change, (int, float)) and change > 0 else "下跌" if isinstance(change, (int, float)) and change < 0 else "持平"
        sign = "+" if isinstance(percent, (int, float)) and percent > 0 else ""
        return (
            f"摘要\n{value('stockName', '股票')}（{value('stockCode')}）目前成交價為 {value('currentPrice')} {value('currency', 'TWD')}，"
            f"相較昨收{direction}，漲跌幅 {sign}{value('changePercent')}%。\n\n"
            "關鍵數據\n"
            f"- 成交價：{value('currentPrice')} {value('currency', 'TWD')}\n"
            f"- 開盤價：{value('openPrice')} {value('currency', 'TWD')}\n"
            f"- 昨收價：{value('previousClose')} {value('currency', 'TWD')}\n"
            f"- 漲跌金額：{value('change')} {value('currency', 'TWD')}\n"
            f"- 漲跌幅：{sign}{value('changePercent')}%\n"
            f"- 資料時間：{value('quoteTime')}（來源：{value('source')}）\n\n"
            "可能影響因素\n- 此問題僅查詢行情，未額外搜尋新聞或推測價格原因。\n\n"
            "資料限制\n- 即時行情可能因資料來源更新頻率而有短暫延遲。"
        )

    def _bounded_fallback_answer(self, traces: list[ToolTrace]) -> str:
        failed = [trace for trace in traces if trace.status != "success"]
        if failed:
            limitations = "\n".join(
                f"- {trace.tool}：{trace.error or '資料來源暫時無法使用'}"
                for trace in failed
            )
        else:
            limitations = "- Agent 已達安全工具呼叫上限，未繼續重複查詢。"

        return (
            "摘要\n"
            "本次研究未能取得足夠的可驗證資料，因此不提供推測性結論。\n\n"
            "關鍵數據\n"
            "- 暫無足夠且可核對的數據。\n\n"
            "可能影響因素\n"
            "- 因資料不足，本次不推測可能影響因素。\n\n"
            "資料限制\n"
            f"{limitations}"
        )

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
