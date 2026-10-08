from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.clients.news import NewsSearchClient, NewsSearchError
from app.clients.market import MarketRankingClient, MarketRankingError
from app.clients.stocktracker import StockTrackerClient, StockTrackerError


@dataclass(frozen=True, slots=True)
class ToolExecution:
    call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    status: str
    duration_ms: int
    error: str | None = None

    def as_function_result(self) -> dict[str, Any]:
        import json

        return {
            "type": "function_result",
            "name": self.name,
            "call_id": self.call_id,
            "result": [{"type": "text", "text": json.dumps(self.result, ensure_ascii=False)}],
        }


class ToolExecutor:
    def __init__(
        self,
        stocktracker: StockTrackerClient,
        news: NewsSearchClient,
        market: MarketRankingClient | None = None,
    ) -> None:
        self._stocktracker = stocktracker
        self._news = news
        self._market = market

    async def execute(
        self, call_id: str, name: str, arguments: dict[str, Any]
    ) -> ToolExecution:
        started = time.perf_counter()
        try:
            if name == "get_stock_snapshot":
                result = await self._stocktracker.get_snapshot(arguments["stock_code"])
            elif name == "get_revenue_history":
                result = await self._stocktracker.get_revenue(
                    arguments["stock_code"], int(arguments.get("months", 12))
                )
            elif name == "search_news":
                result = await self._news.search(
                    arguments["query"],
                    days=int(arguments.get("days", 7)),
                    max_results=int(arguments.get("max_results", 5)),
                    fallback_query=arguments.get("fallback_query"),
                )
            elif name == "get_top_volume":
                if self._market is None:
                    raise MarketRankingError("證交所成交量排行工具未啟用")
                result = await self._market.get_top_volume()
            else:
                raise ValueError(f"Unsupported tool: {name}")
            return ToolExecution(
                call_id=call_id,
                name=name,
                arguments=arguments,
                result=result,
                status="success",
                duration_ms=self._elapsed_ms(started),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            NewsSearchError,
            MarketRankingError,
            StockTrackerError,
        ) as exc:
            error = str(exc)
            return ToolExecution(
                call_id=call_id,
                name=name,
                arguments=arguments,
                result={"error": error},
                status="error",
                duration_ms=self._elapsed_ms(started),
                error=error,
            )

    def _elapsed_ms(self, started: float) -> int:
        return round((time.perf_counter() - started) * 1000)
