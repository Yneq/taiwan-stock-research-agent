from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.session import router as session_router
from app.auth.session import MemberSession, SessionManager, require_session


SECRET = "integration-secret-that-is-at-least-32-chars"


class FakeAuthClient:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.token = jwt.encode(
            {"sub": "vance", "iat": now, "exp": now + timedelta(hours=1)},
            SECRET,
            algorithm="HS256",
        )

    async def login(self, identifier: str, password: str) -> str:
        return self.token

    async def register(self, username: str, email: str, password: str) -> None:
        return None

    async def me(self, token: str) -> dict[str, object]:
        return {"id": 7, "username": "vance", "email": "vance@example.com"}

    async def watchlist(self, token: str) -> list[dict[str, str]]:
        return [{"stockCode": "2330", "market": "twse"}]


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.auth_client = FakeAuthClient()
    app.state.session_manager = SessionManager(SECRET, "finscope_session")
    app.state.session_cookie_secure = False
    app.state.demo_username = "finscope_demo"
    app.state.demo_email = "demo@finscope.tw"
    app.state.demo_password = "server-side-demo-password"
    app.include_router(session_router)

    @app.get("/protected")
    async def protected(session: MemberSession = Depends(require_session)) -> dict[str, str]:
        return {"username": session.username}

    return app


def test_login_keeps_jwt_in_httponly_cookie() -> None:
    client = TestClient(build_app())

    response = client.post(
        "/api/session/login",
        json={"identifier": "vance", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "username": "vance",
        "email": "vance@example.com",
    }
    assert "token" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert client.get("/protected").json() == {"username": "vance"}


def test_protected_endpoint_requires_login_and_logout_clears_session() -> None:
    client = TestClient(build_app())

    assert client.get("/protected").status_code == 401
    client.post(
        "/api/session/login",
        json={"identifier": "vance", "password": "password123"},
    )
    assert client.post("/api/session/logout").status_code == 204
    assert client.get("/protected").status_code == 401


def test_member_watchlist_only_exposes_market_and_stock_code() -> None:
    client = TestClient(build_app())
    client.post(
        "/api/session/login",
        json={"identifier": "vance", "password": "password123"},
    )

    response = client.get("/api/member/watchlist")

    assert response.status_code == 200
    assert response.json() == [{"stockCode": "2330", "market": "twse"}]


def test_demo_login_sets_session_without_returning_credentials() -> None:
    client = TestClient(build_app())

    response = client.post("/api/session/demo")

    assert response.status_code == 200
    assert response.json()["username"] == "vance"
    assert "password" not in response.text
    assert "token" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
