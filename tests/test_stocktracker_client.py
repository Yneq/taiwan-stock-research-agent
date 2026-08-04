from __future__ import annotations

import json

import httpx
import pytest

from app.clients.stocktracker import StockTrackerClient, StockTrackerError


@pytest.mark.asyncio
async def test_sends_agent_key_and_parses_snapshot() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Agent-Key"] == "secret"
        assert request.url.path == "/api/v1/stocks/2330/snapshot"
        return httpx.Response(
            200,
            json={"stockCode": "2330", "currentPrice": 1120, "source": "TWSE MIS"},
        )

    client = StockTrackerClient(
        "https://stock.example", "secret", transport=httpx.MockTransport(handler)
    )
    try:
        result = await client.get_snapshot("2330")
    finally:
        await client.close()

    assert result["currentPrice"] == 1120


@pytest.mark.asyncio
async def test_normalizes_java_error_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            content=json.dumps(
                {"code": "STOCK_NOT_FOUND", "message": "找不到股票代碼 9999"}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )

    client = StockTrackerClient(
        "https://stock.example", "secret", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(StockTrackerError, match="STOCK_NOT_FOUND"):
            await client.get_snapshot("9999")
    finally:
        await client.close()
