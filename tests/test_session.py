from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.auth.session import SessionManager
from app.clients.auth import AuthServiceError, StockTrackerAuthClient


SECRET = "test-secret-that-is-at-least-32-chars-long"


def issue_token(username: str = "vance", *, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    expires = now - timedelta(minutes=1) if expired else now + timedelta(hours=1)
    return jwt.encode({"sub": username, "iat": now, "exp": expires}, SECRET, algorithm="HS256")


def test_session_manager_validates_java_style_jwt() -> None:
    session = SessionManager(SECRET, "finscope_session").decode(issue_token())

    assert session.username == "vance"
    assert session.expires_at > 0


def test_session_manager_rejects_expired_jwt() -> None:
    with pytest.raises(ValueError, match="invalid or expired"):
        SessionManager(SECRET, "finscope_session").decode(issue_token(expired=True))


@pytest.mark.asyncio
async def test_auth_client_logs_in_and_removes_sensitive_watchlist_fields() -> None:
    token = issue_token()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"token": token})
        return httpx.Response(
            200,
            json=[{"id": 9, "userId": 7, "stockCode": "2330", "market": "twse"}],
        )

    client = StockTrackerAuthClient(
        "https://stocktracker.test",
        5,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await client.login("vance", "password") == token
        assert await client.watchlist(token) == [{"stockCode": "2330", "market": "twse"}]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_client_preserves_safe_api_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "帳號或密碼錯誤"})

    client = StockTrackerAuthClient(
        "https://stocktracker.test",
        5,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(AuthServiceError, match="帳號或密碼錯誤") as exc:
            await client.login("vance", "wrong")
        assert exc.value.status_code == 401
    finally:
        await client.close()
