from __future__ import annotations

from typing import Any

import httpx


class AuthServiceError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class StockTrackerAuthClient:
    """HTTP client for Java-owned members, JWTs and watchlists."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def register(self, username: str, email: str, password: str) -> None:
        await self._request(
            "POST",
            "/api/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    async def login(self, identifier: str, password: str) -> str:
        payload = await self._request(
            "POST",
            "/api/auth/login",
            json={"username": identifier, "password": password},
        )
        token = str(payload.get("token", "")).strip() if isinstance(payload, dict) else ""
        if not token:
            raise AuthServiceError(502, "會員服務未回傳登入憑證")
        return token

    async def me(self, token: str) -> dict[str, Any]:
        payload = await self._request("GET", "/api/auth/me", token=token)
        if not isinstance(payload, dict):
            raise AuthServiceError(502, "會員服務回傳格式不正確")
        return {
            "id": payload.get("id"),
            "username": payload.get("username") or "",
            "email": payload.get("email") or "",
        }

    async def watchlist(self, token: str) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/watchlist", token=token)
        if not isinstance(payload, list):
            raise AuthServiceError(502, "自選股服務回傳格式不正確")
        return [
            {
                "stockCode": item.get("stockCode") or "",
                "market": item.get("market") or "",
            }
            for item in payload
            if isinstance(item, dict)
        ]

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, str] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = await self._client.request(
                method,
                path,
                headers=headers,
                json=json,
            )
        except httpx.RequestError as exc:
            raise AuthServiceError(
                503,
                "會員服務正在喚醒或暫時無法連線，請稍後再試",
            ) from exc

        if response.is_success:
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                return {"message": response.text}

        message = self._error_message(response)
        status_code = response.status_code if response.status_code < 500 else 502
        raise AuthServiceError(status_code, message)

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or "會員服務暫時無法完成請求"
        if isinstance(payload, dict):
            return str(
                payload.get("detail")
                or payload.get("error")
                or payload.get("message")
                or "會員服務暫時無法完成請求"
            )
        return "會員服務暫時無法完成請求"
