from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.progress import measured


TOP_VOLUME_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX20"


class MarketRankingError(RuntimeError):
    """Official volume ranking is temporarily unavailable or malformed."""


class MarketRankingClient:
    def __init__(
        self,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @measured("證交所成交量排行")
    async def get_top_volume(self) -> dict[str, Any]:
        try:
            response = await self._client.get(TOP_VOLUME_URL)
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketRankingError("無法取得證交所成交量排行") from exc
        if not isinstance(rows, list):
            raise MarketRankingError("證交所成交量排行格式不正確")

        stocks = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("Code", "")).strip()
            # ETFs and funds can appear in the official top 20. This question
            # asks for an individual listed stock, not an ETF.
            if not re.fullmatch(r"[1-9]\d{3}", code):
                continue
            try:
                rank = int(row["Rank"])
                volume = int(row["TradeVolume"])
                date = datetime.strptime(str(row["Date"]), "%Y%m%d").date()
            except (KeyError, TypeError, ValueError):
                continue
            if not row.get("Name") or volume <= 0:
                continue
            stocks.append({
                "rank": rank,
                "stockCode": code,
                "stockName": str(row["Name"]).strip(),
                "tradeVolumeShares": volume,
                "tradingDate": date.isoformat(),
            })

        stocks.sort(key=lambda item: item["rank"])
        if not stocks:
            raise MarketRankingError("成交量排行沒有可核對的上市個股")

        # The endpoint is a latest-close dataset, not live volume. Reject
        # unexpectedly stale data instead of calling it today's ranking.
        today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        age_days = (today - datetime.fromisoformat(stocks[0]["tradingDate"]).date()).days
        if age_days < 0 or age_days > 7:
            raise MarketRankingError("證交所成交量排行資料日期過舊")

        return {
            "tradingDate": stocks[0]["tradingDate"],
            "stocks": stocks[:5],
            "source": "TWSE OpenAPI：每日成交量前二十名證券",
            "sourceUrl": TOP_VOLUME_URL,
            "limitation": "僅涵蓋上市證券的最近交易日盤後排行，不含上櫃股票及盤中即時成交量。",
        }
