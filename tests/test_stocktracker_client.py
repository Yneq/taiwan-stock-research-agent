from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.clients.stocktracker import StockTrackerClient, StockTrackerError


class FakeMcpSession:
    def __init__(self, result: object, tool_names: list[str] | None = None) -> None:
        self.result = result
        self.tool_names = tool_names or []
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> object:
        self.calls.append((name, arguments))
        return self.result

    async def list_tools(self) -> object:
        return SimpleNamespace(
            tools=[SimpleNamespace(name=name) for name in self.tool_names]
        )


@pytest.mark.asyncio
async def test_calls_snapshot_mcp_tool_and_parses_structured_result() -> None:
    session = FakeMcpSession(
        SimpleNamespace(
            isError=False,
            structuredContent={
                "stockCode": "2330",
                "currentPrice": 1120,
                "source": "TWSE MIS",
            },
            content=[],
        )
    )
    client = StockTrackerClient(
        "https://stock.example", "secret", session=session
    )
    result = await client.get_snapshot("2330")

    assert result["currentPrice"] == 1120
    assert session.calls == [
        ("get_stock_snapshot", {"stockCode": "2330"})
    ]


@pytest.mark.asyncio
async def test_parses_text_fallback_from_mcp_tool() -> None:
    payload = {"stockCode": "2330", "requestedMonths": 2, "data": []}
    session = FakeMcpSession(
        SimpleNamespace(
            isError=False,
            structuredContent=None,
            content=[SimpleNamespace(text=json.dumps(payload))],
        )
    )
    client = StockTrackerClient(
        "https://stock.example", "secret", session=session
    )
    result = await client.get_revenue("2330", 2)

    assert result == payload
    assert session.calls == [
        ("get_revenue_history", {"stockCode": "2330", "months": 2})
    ]


@pytest.mark.asyncio
async def test_normalizes_mcp_tool_error() -> None:
    session = FakeMcpSession(
        SimpleNamespace(
            isError=True,
            structuredContent=None,
            content=[SimpleNamespace(text="STOCK_NOT_FOUND: 找不到股票代碼 9999")],
        )
    )
    client = StockTrackerClient(
        "https://stock.example", "secret", session=session
    )

    with pytest.raises(StockTrackerError, match="STOCK_NOT_FOUND"):
        await client.get_snapshot("9999")


@pytest.mark.asyncio
async def test_discovers_registered_mcp_tools() -> None:
    session = FakeMcpSession(
        SimpleNamespace(isError=False, structuredContent={}, content=[]),
        tool_names=["get_stock_snapshot", "get_revenue_history"],
    )
    client = StockTrackerClient(
        "https://stock.example", "secret", session=session
    )

    assert await client.list_tool_names() == [
        "get_stock_snapshot",
        "get_revenue_history",
    ]


@pytest.mark.asyncio
async def test_warmup_reuses_existing_mcp_session() -> None:
    session = FakeMcpSession(
        SimpleNamespace(isError=False, structuredContent={}, content=[])
    )
    client = StockTrackerClient(
        "https://stock.example", "secret", session=session
    )

    await client.warmup()

    assert client._session is session
    assert client.warmup_url == "https://stock.example/health"


@pytest.mark.asyncio
async def test_waits_for_sleeping_service_to_become_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = iter([503, 200])
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(next(statuses))

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.clients.stocktracker.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as readiness_client:
        client = StockTrackerClient(
            "https://stock.example",
            "secret",
            timeout_seconds=5,
            readiness_client=readiness_client,
        )
        await client._wait_until_ready()

    assert requests == [
        "https://stock.example/health",
        "https://stock.example/health",
    ]
