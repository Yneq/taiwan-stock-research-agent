from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class ToolTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    status: str
    duration_ms: int
    error: str | None = None
    data: dict[str, Any] | None = None


class Citation(BaseModel):
    title: str
    url: str
    cited_text: str | None = None


class ResearchResponse(BaseModel):
    answer: str
    tool_calls: list[ToolTrace]
    citations: list[Citation]
    model: str
    disclaimer: str = (
        "本內容僅整理公開資訊，不構成投資建議；新聞事件與股價變化不代表直接因果關係。"
    )
