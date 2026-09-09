import logging
import asyncio
import json
import time
from contextlib import suppress
from fastapi.responses import StreamingResponse
from app.progress import sink

from fastapi import APIRouter, Depends, HTTPException, Request

from app.agent.orchestrator import AgentIncompleteError, ResearchOrchestrator
from app.auth.session import MemberSession, require_session
from app.clients.gemini import GeminiRateLimitError
from app.schemas.research import ResearchRequest, ResearchResponse


router = APIRouter(prefix="/api", tags=["research"])
logger = logging.getLogger(__name__)


@router.post("/research", response_model=ResearchResponse)
async def research(
    payload: ResearchRequest,
    request: Request,
    _session: MemberSession = Depends(require_session),
) -> ResearchResponse:
    orchestrator: ResearchOrchestrator = request.app.state.orchestrator
    if "application/x-ndjson" in request.headers.get("accept", ""):
        async def events():
            queue = asyncio.Queue()
            started = time.perf_counter()
            def report(event):
                queue.put_nowait({"type": "progress", "elapsed_ms": round((time.perf_counter()-started)*1000), **event})
            async def run():
                token = sink.set(report)
                try:
                    report({"stage": "研究", "status": "started"})
                    async with asyncio.timeout(180):
                        outcome = await orchestrator.research(payload.question)
                    response = ResearchResponse(answer=outcome.answer, tool_calls=outcome.traces,
                                                citations=outcome.citations, model=orchestrator.model)
                    report({"stage": "研究總耗時", "status": "completed", "duration_ms": round((time.perf_counter()-started)*1000)})
                    queue.put_nowait({"type": "result", "data": response.model_dump()})
                except GeminiRateLimitError:
                    queue.put_nowait({"type": "error", "detail": "AI 額度繁忙，自動重試仍未成功，請稍後再試。"})
                except TimeoutError:
                    queue.put_nowait({"type": "error", "detail": "研究已超過 180 秒，請參考階段耗時後重試。"})
                except AgentIncompleteError as exc:
                    queue.put_nowait({"type": "error", "detail": str(exc)})
                except Exception:
                    logger.exception("Streaming research failed")
                    queue.put_nowait({"type": "error", "detail": "研究未完成，請稍後重試。"})
                finally:
                    sink.reset(token)
            task = asyncio.create_task(run())
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=10)
                    except TimeoutError:
                        yield json.dumps({"type": "heartbeat"}) + "\n"
                        continue
                    yield json.dumps(event, ensure_ascii=False) + "\n"
                    if event["type"] in {"result", "error"}:
                        break
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    try:
        outcome = await orchestrator.research(payload.question)
    except GeminiRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="AI 免費額度正在冷卻，系統已自動重試；請稍後再送出。",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except AgentIncompleteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Research request failed")
        raise HTTPException(
            status_code=502,
            detail="AI 研究服務暫時無法完成請求，請稍後再試。",
        ) from exc

    return ResearchResponse(
        answer=outcome.answer,
        tool_calls=outcome.traces,
        citations=outcome.citations,
        model=orchestrator.model,
    )
