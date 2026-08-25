from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ExtractPreviewResponse(BaseModel):
    filename: str
    anchored_text: str
    char_count: int
    sentence_count: int
    section_count: int
    fallback_sentence_count: int = 0
    fallback_ratio: float = 0.0
    layout: str = "single"
    page_count: int = 0


class ReviewCreateResponse(BaseModel):
    id: str
    agent_key: str
    status: str
    overall_score: int | None = None
    weights: dict[str, float] | None = None
    report: dict[str, Any] | None = None
    filename: str | None = None
    created_at: datetime | None = None
    error: str | None = None


class ReviewListItem(BaseModel):
    id: str
    status: str
    overall_score: int | None
    filename: str | None
    job_title: str | None
    created_at: datetime


class ReviewIdsRequest(BaseModel):
    ids: list[str]


class ReviewDeleteResponse(BaseModel):
    deleted: int
