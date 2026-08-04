from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any

import httpx


class StockTrackerError(RuntimeError):
    """A normalized StockTracker client error safe to expose to the model."""


class StockTrackerClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10,
        session: Any | None = None,
    ) -> None:
        self._mcp_url = f"{base_url.rstrip('/')}/mcp"
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._session = session
        self._owns_session = session is None
        self._exit_stack = AsyncExitStack()
        self._connect_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_session:
            await self._exit_stack.aclose()
            self._session = None

    async def get_snapshot(self, stock_code: str) -> dict[str, Any]:
        return await self._call_tool(
            "get_stock_snapshot", {"stockCode": stock_code}
        )

    async def get_revenue(self, stock_code: str, months: int) -> dict[str, Any]:
        return await self._call_tool(
            "get_revenue_history",
            {"stockCode": stock_code, "months": months},
        )

    async def _call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        try:
            result = await session.call_tool(name, arguments)
        except httpx.TimeoutException as exc:
            raise StockTrackerError("StockTracker MCP request timed out") from exc
        except httpx.HTTPError as exc:
            raise StockTrackerError("StockTracker MCP server is unavailable") from exc
        except Exception as exc:
            raise StockTrackerError(f"StockTracker MCP call failed: {exc}") from exc

        return self._decode_tool_result(result)

    async def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session

        async with self._connect_lock:
            if self._session is not None:
                return self._session

            try:
                from mcp import ClientSession
                from mcp.client.streamable_http import streamable_http_client

                http_client = await self._exit_stack.enter_async_context(
                    httpx.AsyncClient(
                        headers={"X-Agent-Key": self._api_key},
                        timeout=self._timeout_seconds,
                    )
                )
                read_stream, write_stream, _ = await self._exit_stack.enter_async_context(
                    streamable_http_client(
                        self._mcp_url,
                        http_client=http_client,
                    )
                )
                session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                self._session = session
            except Exception as exc:
                await self._exit_stack.aclose()
                self._exit_stack = AsyncExitStack()
                raise StockTrackerError(
                    f"Unable to connect to StockTracker MCP server: {exc}"
                ) from exc

        return self._session

    def _decode_tool_result(self, result: Any) -> dict[str, Any]:
        if getattr(result, "isError", False) or getattr(result, "is_error", False):
            raise StockTrackerError(self._result_text(result) or "MCP tool returned an error")

        structured = getattr(result, "structuredContent", None)
        if structured is None:
            structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            return structured

        text = self._result_text(result)
        if not text:
            raise StockTrackerError("MCP tool returned an empty response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StockTrackerError("MCP tool returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise StockTrackerError("MCP tool returned an unexpected response")
        return data

    def _result_text(self, result: Any) -> str:
        texts: list[str] = []
        for item in getattr(result, "content", []):
            text = getattr(item, "text", None)
            if isinstance(text, str):
                texts.append(text)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        return "\n".join(texts)
