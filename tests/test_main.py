from __future__ import annotations

import asyncio

import pytest

from app.main import MARKET_TICKER_CODES, app, market_ticker


class FakeStockTracker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_snapshot(self, stock_code: str) -> dict[str, object]:
        self.calls.append(stock_code)
        return {
            "stockCode": stock_code,
            "stockName": f"股票 {stock_code}",
            "currentPrice": 100.0,
            "changePercent": 1.25,
            "currency": "TWD",
        }


@pytest.mark.asyncio
async def test_market_ticker_uses_cached_mcp_snapshots() -> None:
    stocktracker = FakeStockTracker()
    app.state.stocktracker = stocktracker
    app.state.market_ticker_cache = []
    app.state.market_ticker_cached_at = 0.0
    app.state.market_ticker_lock = asyncio.Lock()

    first = await market_ticker()
    second = await market_ticker()

    assert [item["stockCode"] for item in first["items"]] == list(MARKET_TICKER_CODES)
    assert second == first
    assert stocktracker.calls == list(MARKET_TICKER_CODES)
