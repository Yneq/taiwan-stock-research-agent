from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.clients.market import MarketRankingClient, MarketRankingError, TOP_VOLUME_URL
from app.tools.executor import ToolExecutor


def client_for(rows) -> MarketRankingClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=rows)
    ))
    return MarketRankingClient(client=http)


@pytest.mark.asyncio
async def test_uses_latest_listed_common_stock_not_etf() -> None:
    date = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y%m%d")
    client = client_for([
        {"Date": date, "Rank": "1", "Code": "0050", "Name": "ETF", "TradeVolume": "9000"},
        {"Date": date, "Rank": "3", "Code": "3481", "Name": "群創", "TradeVolume": "3000"},
        {"Date": date, "Rank": "2", "Code": "2409", "Name": "友達", "TradeVolume": "5000"},
    ])

    result = await client.get_top_volume()

    assert result["stocks"][0]["stockCode"] == "2409"
    assert result["stocks"][0]["tradeVolumeShares"] == 5000
    assert result["sourceUrl"] == TOP_VOLUME_URL
    assert "不含上櫃" in result["limitation"]


@pytest.mark.asyncio
async def test_rejects_stale_ranking() -> None:
    old = (datetime.now(ZoneInfo("Asia/Taipei")) - timedelta(days=10)).strftime("%Y%m%d")
    client = client_for([
        {"Date": old, "Rank": "1", "Code": "2409", "Name": "友達", "TradeVolume": "5000"}
    ])

    with pytest.raises(MarketRankingError, match="過舊"):
        await client.get_top_volume()


@pytest.mark.asyncio
async def test_rejects_malformed_ranking() -> None:
    with pytest.raises(MarketRankingError, match="格式"):
        await client_for({"unexpected": "object"}).get_top_volume()


@pytest.mark.asyncio
async def test_tool_executor_exposes_official_ranking_result() -> None:
    class FakeMarket:
        async def get_top_volume(self):
            return {"stocks": [{"stockCode": "2409"}], "sourceUrl": TOP_VOLUME_URL}

    executor = ToolExecutor(stocktracker=object(), news=object(), market=FakeMarket())
    execution = await executor.execute("volume-1", "get_top_volume", {})

    assert execution.status == "success"
    assert execution.result["stocks"][0]["stockCode"] == "2409"
