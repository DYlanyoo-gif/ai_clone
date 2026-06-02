from __future__ import annotations

"""
Easy Dataset Adapter (SKELETON)

Easy Dataset is a tool for creating fine-tuning, RAG evaluation, and
benchmark datasets from raw text. It's NOT installed by default.

This adapter provides a simple export function that converts profile chunks
into JSONL format suitable for downstream dataset tools.

Current state: exports chunks as JSON array (does not require Easy Dataset).
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import Chunk, AnalysisReport, ChatMessage

logger = logging.getLogger(__name__)


def export_chunks_jsonl(
    db: Session,
    profile_id: int,
    include_chat: bool = True,
) -> list[dict]:
    """Export profile data as a list of dicts suitable for JSONL output.

    Each entry includes chunk content and metadata. If include_chat is True,
    chat message pairs (user + assistant) are also included as training examples.

    This is a lightweight MVP export — Easy Dataset itself is not required.
    """
    result: list[dict] = []

    # Export chunks
    chunks = (
        db.query(Chunk)
        .filter(Chunk.profile_id == profile_id)
        .order_by(Chunk.chunk_index)
        .all()
    )
    for c in chunks:
        result.append({
            "type": "chunk",
            "profile_id": profile_id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "char_count": c.char_count,
        })

    # Export analysis
    analysis = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    if analysis:
        result.append({
            "type": "analysis",
            "profile_id": profile_id,
            "portrait_report": analysis.portrait_report,
            "style_card": analysis.style_card,
        })

    # Export chat pairs for fine-tuning
    if include_chat:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.profile_id == profile_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        for i in range(0, len(messages) - 1, 2):
            if messages[i].role == "user" and messages[i + 1].role == "assistant":
                result.append({
                    "type": "chat_pair",
                    "profile_id": profile_id,
                    "user": messages[i].content,
                    "assistant": messages[i + 1].content,
                })

    return result
