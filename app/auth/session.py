from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, Request, status


@dataclass(frozen=True, slots=True)
class MemberSession:
    token: str
    username: str
    expires_at: int


class SessionManager:
    """Validates the Java-issued JWT before a protected Python endpoint runs."""

    def __init__(self, secret: str, cookie_name: str) -> None:
        self._secret = secret
        self.cookie_name = cookie_name

    def decode(self, token: str) -> MemberSession:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256", "HS384", "HS512"],
                options={"require": ["sub", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise ValueError("invalid or expired member session") from exc

        username = str(claims.get("sub", "")).strip()
        if not username:
            raise ValueError("member session has no subject")
        return MemberSession(
            token=token,
            username=username,
            expires_at=int(claims["exp"]),
        )


async def require_session(request: Request) -> MemberSession:
    manager: SessionManager = request.app.state.session_manager
    token = request.cookies.get(manager.cookie_name, "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="請先登入會員再開始研究",
        )
    try:
        return manager.decode(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入已失效，請重新登入",
        ) from exc
