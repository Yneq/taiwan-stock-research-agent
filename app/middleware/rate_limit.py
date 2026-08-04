from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class ResearchRateLimitMiddleware(BaseHTTPMiddleware):
    """Small single-instance limiter for a public portfolio demo."""

    def __init__(self, app, requests_per_minute: int = 6) -> None:
        super().__init__(app)
        self._limit = requests_per_minute
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method != "POST" or request.url.path != "/api/research":
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",", 1)[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        now = time.monotonic()
        async with self._lock:
            history = self._requests[client_ip]
            while history and now - history[0] >= 60:
                history.popleft()
            if len(history) >= self._limit:
                retry_after = max(1, round(60 - (now - history[0])))
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "detail": "Demo 使用次數較多，請稍後再試。",
                        "retry_after_seconds": retry_after,
                    },
                )
            history.append(now)

        return await call_next(request)
