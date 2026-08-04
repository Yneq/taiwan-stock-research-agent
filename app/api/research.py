import logging

from fastapi import APIRouter, HTTPException, Request

from app.agent.orchestrator import AgentIncompleteError, ResearchOrchestrator
from app.schemas.research import ResearchRequest, ResearchResponse


router = APIRouter(prefix="/api", tags=["research"])
logger = logging.getLogger(__name__)


@router.post("/research", response_model=ResearchResponse)
async def research(payload: ResearchRequest, request: Request) -> ResearchResponse:
    orchestrator: ResearchOrchestrator = request.app.state.orchestrator
    try:
        outcome = await orchestrator.research(payload.question)
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
