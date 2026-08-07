from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.orchestrator import ResearchOrchestrator
from app.api.research import router as research_router
from app.api.session import router as session_router
from app.auth.session import SessionManager
from app.clients.auth import StockTrackerAuthClient
from app.clients.gemini import GeminiInteractionsGateway
from app.clients.news import NewsSearchClient
from app.clients.stocktracker import StockTrackerClient
from app.config import get_settings
from app.middleware.rate_limit import ResearchRateLimitMiddleware
from app.tools.executor import ToolExecutor


STATIC_DIR = Path(__file__).resolve().parent / "static"
logger = logging.getLogger(__name__)
MARKET_TICKER_CODES = ("2330", "2454", "2317", "6488", "2308", "3231")
MARKET_TICKER_CACHE_SECONDS = 300


async def warm_stocktracker(stocktracker: StockTrackerClient) -> None:
    try:
        await stocktracker.warmup()
    except Exception:
        logger.warning("Background StockTracker warmup failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    stocktracker = StockTrackerClient(
        base_url=settings.stocktracker_base_url,
        api_key=settings.stocktracker_api_key,
        timeout_seconds=settings.request_timeout_seconds,
    )
    gateway = GeminiInteractionsGateway(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )
    news = NewsSearchClient(timeout_seconds=settings.request_timeout_seconds)
    auth_client = StockTrackerAuthClient(
        base_url=settings.stocktracker_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )
    app.state.orchestrator = ResearchOrchestrator(
        gateway=gateway,
        executor=ToolExecutor(stocktracker, news),
        max_steps=settings.max_agent_steps,
    )
    app.state.stocktracker = stocktracker
    app.state.auth_client = auth_client
    app.state.session_manager = SessionManager(
        secret=settings.jwt_secret,
        cookie_name=settings.session_cookie_name,
    )
    app.state.session_cookie_secure = settings.session_cookie_secure
    app.state.stocktracker_warmup_task = None
    app.state.market_ticker_cache = []
    app.state.market_ticker_cached_at = 0.0
    app.state.market_ticker_lock = asyncio.Lock()
    yield
    warmup_task = app.state.stocktracker_warmup_task
    if warmup_task is not None and not warmup_task.done():
        warmup_task.cancel()
        try:
            await warmup_task
        except asyncio.CancelledError:
            pass
    await stocktracker.close()
    await auth_client.close()
    await news.close()


app = FastAPI(
    title="Taiwan Stock Research Agent",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(ResearchRateLimitMiddleware, requests_per_minute=6)
app.include_router(research_router)
app.include_router(session_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/warmup",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["operations"],
)
async def warmup() -> dict[str, str]:
    task = app.state.stocktracker_warmup_task
    if task is None or task.done():
        app.state.stocktracker_warmup_task = asyncio.create_task(
            warm_stocktracker(app.state.stocktracker)
        )
    return {
        "status": "warming",
        "wake_url": app.state.stocktracker.warmup_url,
    }


@app.get("/api/market-ticker", tags=["market-data"])
async def market_ticker() -> dict[str, list[dict[str, object]]]:
    async with app.state.market_ticker_lock:
        now = time.monotonic()
        cached = app.state.market_ticker_cache
        if cached and now - app.state.market_ticker_cached_at < MARKET_TICKER_CACHE_SECONDS:
            return {"items": cached}

        items: list[dict[str, object]] = []
        for stock_code in MARKET_TICKER_CODES:
            try:
                snapshot = await app.state.stocktracker.get_snapshot(stock_code)
            except Exception:
                logger.info("Ticker snapshot unavailable for %s", stock_code, exc_info=True)
                continue
            items.append(
                {
                    "stockCode": snapshot.get("stockCode", stock_code),
                    "stockName": snapshot.get("stockName", ""),
                    "currentPrice": snapshot.get("currentPrice"),
                    "changePercent": snapshot.get("changePercent"),
                    "currency": snapshot.get("currency", "TWD"),
                    "quoteTime": snapshot.get("quoteTime"),
                }
            )

        if items:
            app.state.market_ticker_cache = items
            app.state.market_ticker_cached_at = now
        return {"items": items}
