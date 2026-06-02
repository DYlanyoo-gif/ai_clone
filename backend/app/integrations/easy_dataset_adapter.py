from __future__ import annotations

"""
Easy Dataset Adapter — export chunks as standard JSONL for RAG datasets.

Easy Dataset (github.com/ConardLi/easy-dataset) is a tool for creating
fine-tuning, RAG evaluation, and benchmark datasets from raw text.
It is NOT installed in this project — we only export compatible formats.

Each JSONL line:
{
  "profile_id": int,
  "profile_name": str,
  "source_document": str,
  "chunk_id": int,
  "text": str,
  "metadata": {
    "relationship_type": str,
    "parser": str,
    "char_count": int,
    "created_at": str
  }
}
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import Chunk, AnalysisReport, ChatMessage, Profile, Document

logger = logging.getLogger(__name__)


def export_rag_dataset(
    db: Session,
    profile_id: int,
) -> list[dict]:
    """Export chunks as standard RAG dataset JSONL format.

    Each line is a self-contained document suitable for:
    - Easy Dataset ingestion
    - RAG evaluation benchmarks
    - Embedding pipelines
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return []

    # Build a lookup: chunk_id → document filename
    chunks = (
        db.query(Chunk)
        .filter(Chunk.profile_id == profile_id)
        .order_by(Chunk.chunk_index)
        .all()
    )

    doc_lookup: dict[int, str] = {}
    if chunks:
        doc_ids = list(set(c.document_id for c in chunks))
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        doc_lookup = {d.id: d.filename for d in docs}

    result: list[dict] = []
    for c in chunks:
        result.append({
            "profile_id": profile_id,
            "profile_name": profile.name,
            "source_document": doc_lookup.get(c.document_id, "unknown"),
            "chunk_id": c.id,
            "text": c.content,
            "metadata": {
                "relationship_type": profile.relationship_type,
                "parser": "builtin",  # chunks are always post-parse
                "char_count": c.char_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            },
        })

    return result


def export_chunks_jsonl(
    db: Session,
    profile_id: int,
    include_chat: bool = True,
) -> list[dict]:
    """Legacy export — delegates to export_rag_dataset and appends chat pairs.

    Kept for backward compatibility with existing /export/dataset endpoint.
    """
    result = export_rag_dataset(db, profile_id)

    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    # Export analysis as metadata entry
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
            "profile_name": profile.name if profile else "",
            "source_document": "analysis_report",
            "chunk_id": analysis.id,
            "text": analysis.style_card or analysis.portrait_report or "",
            "metadata": {
                "relationship_type": profile.relationship_type if profile else "",
                "parser": "ai_generated",
                "char_count": len(analysis.style_card or "") + len(analysis.portrait_report or ""),
                "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            },
        })

    # Export chat pairs
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
                    "profile_name": profile.name if profile else "",
                    "source_document": "chat_history",
                    "chunk_id": messages[i].id,
                    "text": f"User: {messages[i].content}\nAssistant: {messages[i + 1].content}",
                    "metadata": {
                        "relationship_type": profile.relationship_type if profile else "",
                        "parser": "chat_export",
                        "char_count": len(messages[i].content) + len(messages[i + 1].content),
                        "created_at": messages[i].created_at.isoformat() if messages[i].created_at else None,
                    },
                })

    return result
