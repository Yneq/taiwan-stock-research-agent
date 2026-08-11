from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.session import router as session_router
from app.auth.session import MemberSession, SessionManager, require_session
from app.clients.auth import AuthServiceError


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


class FirstUseDemoAuthClient(FakeAuthClient):
    def __init__(self) -> None:
        super().__init__()
        self.login_attempts = 0
        self.register_calls: list[tuple[str, str, str]] = []

    async def login(self, identifier: str, password: str) -> str:
        self.login_attempts += 1
        if self.login_attempts == 1:
            raise AuthServiceError(401, "帳號或密碼錯誤")
        return self.token

    async def register(self, username: str, email: str, password: str) -> None:
        self.register_calls.append((username, email, password))


def build_app(auth_client: FakeAuthClient | None = None) -> FastAPI:
    app = FastAPI()
    app.state.auth_client = auth_client or FakeAuthClient()
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


def test_session_status_is_null_for_anonymous_user() -> None:
    client = TestClient(build_app())

    response = client.get("/api/session/status")

    assert response.status_code == 200
    assert response.json() is None


def test_session_status_returns_logged_in_member() -> None:
    client = TestClient(build_app())
    client.post(
        "/api/session/login",
        json={"identifier": "vance", "password": "password123"},
    )

    response = client.get("/api/session/status")

    assert response.status_code == 200
    assert response.json()["username"] == "vance"


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


def test_first_demo_login_registers_java_member_then_retries_login() -> None:
    auth_client = FirstUseDemoAuthClient()
    client = TestClient(build_app(auth_client))

    response = client.post("/api/session/demo")

    assert response.status_code == 200
    assert auth_client.login_attempts == 2
    assert auth_client.register_calls == [
        ("finscope_demo", "demo@finscope.tw", "server-side-demo-password")
    ]
    assert "password" not in response.text
    assert "token" not in response.text


def test_existing_demo_member_does_not_register_again() -> None:
    auth_client = FirstUseDemoAuthClient()
    auth_client.login_attempts = 1
    client = TestClient(build_app(auth_client))

    response = client.post("/api/session/demo")

    assert response.status_code == 200
    assert auth_client.login_attempts == 2
    assert auth_client.register_calls == []
