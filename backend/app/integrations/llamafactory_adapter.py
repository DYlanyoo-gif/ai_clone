from __future__ import annotations

"""
LLaMA Factory Adapter — export SFT data in standard messages format.

LLaMA Factory (github.com/hiyouga/LLaMA-Factory) is a framework for
fine-tuning LLMs (LoRA, QLoRA, full fine-tune). It is NOT installed
in this project — requires PyTorch, transformers, GPU.

This adapter exports chat data in the standard LLaMA Factory format:
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import ChatMessage, AnalysisReport, Profile, Chunk

logger = logging.getLogger(__name__)


def export_sft_dataset(
    db: Session,
    profile_id: int,
    system_prompt: Optional[str] = None,
) -> list[dict]:
    """Export chat messages in LLaMA Factory SFT format.

    Returns list of {messages: [{role, content}, ...]} dicts.
    Each entry has system/user/assistant roles, ready for LLaMA Factory's
    dataset_info.json configuration.

    If no chat messages exist, generates training examples from the analysis
    report and document chunks to bootstrap SFT data.
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return []

    latest_analysis = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )

    if system_prompt is None:
        style_card = ""
        if latest_analysis and latest_analysis.style_card:
            style_card = latest_analysis.style_card

        system_prompt = (
            f"你正在模拟 {profile.name} 的 AI 角色。"
            f"这是基于用户上传资料生成的模拟角色，不代表本人真实意愿。\n\n"
            f"风格卡:\n{style_card[:2000] if style_card else '尚未生成风格卡'}\n\n"
            f"关系类型: {profile.relationship_type}\n"
            f"角色描述: {profile.description or '无'}"
        )

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.profile_id == profile_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    results: list[dict] = []

    # Export real chat pairs as training data
    i = 0
    while i < len(messages) - 1:
        if messages[i].role == "user" and messages[i + 1].role == "assistant":
            results.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": messages[i].content},
                    {"role": "assistant", "content": messages[i + 1].content},
                ],
            })
            i += 2
        else:
            i += 1

    # If no chat data, generate bootstrapping SFT entries from analysis + chunks
    if not results and latest_analysis and latest_analysis.style_card:
        chunks = (
            db.query(Chunk)
            .filter(Chunk.profile_id == profile_id)
            .order_by(Chunk.chunk_index)
            .limit(10)
            .all()
        )
        if chunks:
            # Entry 1: Summarize the person's style
            combined_text = "\n\n".join(c.content[:500] for c in chunks[:5])
            results.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"根据以下资料，总结{profile.name}的语言风格和性格特点：\n\n{combined_text}"},
                    {"role": "assistant", "content": latest_analysis.style_card[:2000]},
                ],
            })

            # Entry 2: Communication advice
            if len(chunks) > 3:
                more_text = "\n\n".join(c.content[:300] for c in chunks[3:8])
                results.append({
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"如何与{profile.name}更好地沟通？请基于以下资料给出建议：\n\n{more_text}"},
                        {"role": "assistant", "content": (
                            latest_analysis.portrait_report[:2000]
                            if latest_analysis.portrait_report
                            else "资料不足，建议上传更多对话样本。"
                        )},
                    ],
                })

    return results


def export_sft_jsonl(
    db: Session,
    profile_id: int,
    system_prompt: Optional[str] = None,
) -> str:
    """Export as JSONL string, one line per training example."""
    data = export_sft_dataset(db, profile_id, system_prompt)
    return "\n".join(json.dumps(entry, ensure_ascii=False) for entry in data)
