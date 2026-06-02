from __future__ import annotations

"""
LLaMA Factory Adapter (SKELETON)

LLaMA Factory is a framework for fine-tuning LLMs (LoRA, QLoRA, full fine-tune).
It's NOT installed in this MVP — requires PyTorch, transformers, etc.

This adapter provides an export function to create SFT (Supervised Fine-Tuning)
datasets in JSONL format, ready for LLaMA Factory consumption.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import ChatMessage, AnalysisReport, Profile

logger = logging.getLogger(__name__)


def export_sft_dataset(
    db: Session,
    profile_id: int,
    system_prompt: Optional[str] = None,
) -> list[dict]:
    """Export chat messages in LLaMA Factory SFT format.

    Each entry is a {messages: [...]} dict with system, user, assistant roles.

    Usage after export:
        - Save as .jsonl file
        - Load into LLaMA Factory's dataset_info.json
        - Run LoRA/QLoRA fine-tuning

    This is a lightweight MVP export — LLaMA Factory itself is not installed.
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
        system_prompt = (
            f"你正在模拟 {profile.name} 的 AI 角色。"
            f"这是基于资料生成的模拟，并非本人。"
        )
        if latest_analysis and latest_analysis.style_card:
            system_prompt += f"\n\n{latest_analysis.style_card[:500]}"

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.profile_id == profile_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    results: list[dict] = []
    for i in range(0, len(messages) - 1, 2):
        if messages[i].role == "user" and messages[i + 1].role == "assistant":
            results.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": messages[i].content},
                    {"role": "assistant", "content": messages[i + 1].content},
                ],
            })

    return results
