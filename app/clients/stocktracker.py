from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class StockTrackerError(RuntimeError):
    """A normalized StockTracker client error safe to expose to the model."""


class StockTrackerClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10,
        session: Any | None = None,
        readiness_client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        self._mcp_url = f"{normalized_base_url}/mcp"
        self._health_url = f"{normalized_base_url}/health"
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._session = session
        self._owns_session = session is None
        self._readiness_client = readiness_client
        self._owns_readiness_client = readiness_client is None
        self._exit_stack = AsyncExitStack()
        self._connect_lock = asyncio.Lock()

    @property
    def warmup_url(self) -> str:
        return self._health_url

    async def close(self) -> None:
        if self._owns_session:
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.debug("MCP session cleanup failed", exc_info=True)
            self._session = None
        if self._owns_readiness_client and self._readiness_client is not None:
            await self._readiness_client.aclose()
            self._readiness_client = None

    async def get_snapshot(self, stock_code: str) -> dict[str, Any]:
        return await self._call_tool(
            "get_stock_snapshot", {"stockCode": stock_code}
        )

    async def get_revenue(self, stock_code: str, months: int) -> dict[str, Any]:
        return await self._call_tool(
            "get_revenue_history",
            {"stockCode": stock_code, "months": months},
        )

    async def list_tool_names(self) -> list[str]:
        session = await self._ensure_session()
        try:
            result = await session.list_tools()
        except Exception as exc:
            raise StockTrackerError(f"Unable to list StockTracker MCP tools: {exc}") from exc
        return [tool.name for tool in result.tools]

    async def warmup(self) -> None:
        """Wake the data service and establish the reusable MCP session."""
        await self._ensure_session()

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
                await self._wait_until_ready()
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

    async def _wait_until_ready(self) -> None:
        """Wake a sleeping free-tier data service before opening MCP streams."""
        if self._readiness_client is None:
            self._readiness_client = httpx.AsyncClient(
                headers={"X-Agent-Key": self._api_key},
                timeout=min(10.0, self._timeout_seconds),
                follow_redirects=True,
            )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_seconds
        while True:
            try:
                response = await self._readiness_client.get(self._health_url)
                if response.is_success:
                    return
            except httpx.HTTPError:
                pass

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise StockTrackerError(
                    "StockTracker service did not become ready before timeout"
                )
            await asyncio.sleep(min(2.0, remaining))

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
