from __future__ import annotations

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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Agent-Key": api_key},
            timeout=timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_snapshot(self, stock_code: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/stocks/{stock_code}/snapshot")

    async def get_revenue(self, stock_code: str, months: int) -> dict[str, Any]:
        return await self._get(
            f"/api/v1/stocks/{stock_code}/revenue", params={"months": months}
        )

    async def _get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.get(path, **kwargs)
        except httpx.TimeoutException as exc:
            raise StockTrackerError("StockTracker request timed out") from exc
        except httpx.HTTPError as exc:
            raise StockTrackerError("StockTracker is unavailable") from exc

        if response.is_error:
            try:
                error = response.json()
                message = error.get("message", "StockTracker request failed")
                code = error.get("code", "UNKNOWN_ERROR")
            except ValueError:
                message = "StockTracker returned an invalid error response"
                code = "INVALID_RESPONSE"
            raise StockTrackerError(f"{code}: {message}")

        try:
            data = response.json()
        except ValueError as exc:
            raise StockTrackerError("StockTracker returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise StockTrackerError("StockTracker returned an unexpected response")
        return data
