from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.orchestrator import ResearchOrchestrator
from app.api.research import router as research_router
from app.clients.gemini import GeminiInteractionsGateway
from app.clients.news import NewsSearchClient
from app.clients.stocktracker import StockTrackerClient
from app.config import get_settings
from app.middleware.rate_limit import ResearchRateLimitMiddleware
from app.tools.executor import ToolExecutor


STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    app.state.orchestrator = ResearchOrchestrator(
        gateway=gateway,
        executor=ToolExecutor(stocktracker, news),
        max_steps=settings.max_agent_steps,
    )
    yield
    await stocktracker.close()
    await news.close()


app = FastAPI(
    title="Taiwan Stock Research Agent",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(ResearchRateLimitMiddleware, requests_per_minute=6)
app.include_router(research_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
