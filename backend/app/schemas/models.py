from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Profile ──
class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    relationship_type: str = Field(default="other", max_length=100)


class ProfileResponse(BaseModel):
    id: int
    name: str
    description: str
    relationship_type: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    chunk_count: int = 0
    has_analysis: bool = False

    model_config = {"from_attributes": True}


class ProfileDetail(ProfileResponse):
    total_chars: int = 0
    latest_portrait: Optional[str] = None
    latest_style_card: Optional[str] = None


# ── Document ──
class DocumentResponse(BaseModel):
    id: int
    profile_id: int
    filename: str
    file_type: str
    content_type: str
    char_count: int
    chunk_count: int
    parser: Optional[str] = None
    parse_status: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# ── Analysis ──
class AnalysisResponse(BaseModel):
    id: int
    profile_id: int
    portrait_report: str
    style_card: str
    total_chunks: int
    total_chars: int
    model_used: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Chat ──
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    mode: str = Field(
        default="daily_chat",
        pattern=r"^(daily_chat|deep_analysis|comfort|advice|style_clone|communication_strategy)$",
    )


class ChatResponse(BaseModel):
    reply: str
    profile_name: str
    retrieved_count: int = 0
    model_used: str = ""


class ChatMessageResponse(BaseModel):
    id: int
    profile_id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Generic ──
class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class MineruStatusResponse(BaseModel):
    installed: bool
    command: Optional[str] = None
    version_or_help: Optional[str] = None
    error: Optional[str] = None
    enabled: bool
    backend: str = "pipeline"
    method: str = "auto"
    lang: str = "ch"
    formula: bool = True
    table: bool = True
    image_analysis: bool = False
    timeout_seconds: int = 300


class Mem0StatusResponse(BaseModel):
    installed: bool
    enabled: bool
    provider: str = "local"
    error: Optional[str] = None


class MemoryRebuildResponse(BaseModel):
    stored: int
    error: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
