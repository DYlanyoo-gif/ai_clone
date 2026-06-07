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
    "created_at": str,
    "filename": str,
    "evidence": { ... }  // if evidence_map exists
  }
}
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import Chunk, AnalysisReport, ChatMessage, Profile, Document

logger = logging.getLogger(__name__)


def _get_evidence_lookup(db: Session, profile_id: int) -> dict:
    """Build a lookup: chunk_index -> evidence info from the latest analysis."""
    latest = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    if not latest or not latest.evidence_json:
        return {}
    try:
        ev_map = json.loads(latest.evidence_json)
        lookup = {}
        for mod_key, mod_data in ev_map.items():
            if isinstance(mod_data, dict):
                for claim in mod_data.get("claims", []):
                    if isinstance(claim, dict):
                        for ev in claim.get("evidence", []):
                            if isinstance(ev, dict):
                                ci = ev.get("chunk_index")
                                if ci is not None:
                                    if ci not in lookup:
                                        lookup[ci] = []
                                    lookup[ci].append({
                                        "module": mod_data.get("module_name", mod_key),
                                        "claim": claim.get("claim", ""),
                                        "quote": ev.get("quote", ""),
                                        "confidence": claim.get("confidence_score", 0),
                                    })
        return lookup
    except (json.JSONDecodeError, Exception):
        return {}


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

    # Build evidence lookup
    evidence_lookup = _get_evidence_lookup(db, profile_id)

    # Build a lookup: chunk_id → document info
    chunks = (
        db.query(Chunk)
        .filter(Chunk.profile_id == profile_id)
        .order_by(Chunk.chunk_index)
        .all()
    )

    doc_lookup: dict[int, dict] = {}
    if chunks:
        doc_ids = list(set(c.document_id for c in chunks))
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        doc_lookup = {d.id: {"filename": d.filename, "parser": d.parser} for d in docs}

    result: list[dict] = []
    for c in chunks:
        doc_info = doc_lookup.get(c.document_id, {"filename": "unknown", "parser": "builtin"})
        chunk_evidence = evidence_lookup.get(c.chunk_index, [])

        entry = {
            "profile_id": profile_id,
            "profile_name": profile.name,
            "source_document": doc_info.get("filename", "unknown"),
            "chunk_id": c.id,
            "chunk_index": c.chunk_index,
            "text": c.content,
            "metadata": {
                "relationship_type": profile.relationship_type,
                "parser": doc_info.get("parser", c.parser or "builtin"),
                "char_count": c.char_count,
                "filename": doc_info.get("filename", "unknown"),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "evidence": chunk_evidence if chunk_evidence else None,
            },
        }
        result.append(entry)

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
                "filename": "analysis_report",
                "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
                "has_evidence": bool(analysis.evidence_json),
                "evidence_summary": _summarize_evidence(analysis.evidence_json) if analysis.evidence_json else None,
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
                        "filename": "chat_history",
                        "created_at": messages[i].created_at.isoformat() if messages[i].created_at else None,
                        "evidence": None,
                    },
                })

    return result


def _summarize_evidence(evidence_json: str) -> Optional[dict]:
    """Create a summary of evidence for metadata."""
    try:
        ev = json.loads(evidence_json)
        total_claims = 0
        total_conf = 0
        modules = []
        for mod_key, mod_data in ev.items():
            if isinstance(mod_data, dict):
                modules.append(mod_data.get("module_name", mod_key))
                claims = mod_data.get("claims", [])
                total_claims += len(claims)
                for c in claims:
                    if isinstance(c, dict):
                        total_conf += c.get("confidence_score", 0)
        return {
            "modules_with_data": len([m for m in ev.values() if isinstance(m, dict) and m.get("data_sufficient")]),
            "total_modules": len(ev),
            "total_claims": total_claims,
            "avg_confidence": round(total_conf / total_claims, 1) if total_claims > 0 else 0,
            "modules": modules,
        }
    except Exception:
        return None
