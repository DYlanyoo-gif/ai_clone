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

If evidence_map exists, also includes evidence-backed SFT samples.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import ChatMessage, AnalysisReport, Profile, Chunk, Document

logger = logging.getLogger(__name__)


def _build_evidence_samples(
    db: Session,
    profile_id: int,
    profile_name: str,
    system_prompt: str,
    latest_analysis: AnalysisReport,
) -> list[dict]:
    """Generate evidence-backed SFT samples from the evidence_map."""
    if not latest_analysis.evidence_json:
        return []
    try:
        ev_map = json.loads(latest_analysis.evidence_json)
    except (json.JSONDecodeError, Exception):
        return []

    # Build chunk lookup
    doc_lookup = {}
    all_chunks = (
        db.query(Chunk, Document.filename)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )
    chunk_by_index = {}
    for chunk, filename in all_chunks:
        chunk_by_index[chunk.chunk_index] = {"content": chunk.content, "filename": filename}

    samples = []

    for mod_key, mod_data in ev_map.items():
        if not isinstance(mod_data, dict) or not mod_data.get("data_sufficient"):
            continue
        module_name = mod_data.get("module_name", mod_key)
        for claim in mod_data.get("claims", []):
            if not isinstance(claim, dict):
                continue
            evidence_quotes = []
            for ev in claim.get("evidence", []):
                if isinstance(ev, dict):
                    chunk_idx = ev.get("chunk_index")
                    chunk_info = chunk_by_index.get(chunk_idx, {})
                    evidence_quotes.append(
                        f"[来源: {chunk_info.get('filename', '未知')}] {ev.get('quote', '')}"
                    )

            if not evidence_quotes:
                continue

            evidence_text = "\n".join(evidence_quotes)
            claim_text = claim.get("claim", "")
            confidence = claim.get("confidence_score", 0)
            data_gap = claim.get("data_gap")
            contradiction = claim.get("contradiction")

            # Sample: user asks "基于什么证据判断X"
            question = f"基于哪些证据，你认为{profile_name}在「{module_name}」方面的特点是：{claim_text}"
            answer_parts = [
                f"这一判断基于 {len(evidence_quotes)} 处资料证据（置信度：{confidence}/100）：",
                evidence_text,
            ]
            if contradiction:
                answer_parts.append(f"注意：资料中也存在矛盾表达：{contradiction}")
            if data_gap:
                answer_parts.append(f"资料不足项：{data_gap}")

            samples.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": "\n\n".join(answer_parts)},
                ],
            })

    return samples[:10]  # Limit evidence samples


def export_sft_dataset(
    db: Session,
    profile_id: int,
    system_prompt: Optional[str] = None,
) -> list[dict]:
    """Export chat messages in LLaMA Factory SFT format.

    Returns list of {messages: [{role, content}, ...]} dicts.
    Includes evidence-backed samples if evidence_map exists.
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

    # Add evidence-backed SFT samples from evidence_map
    if latest_analysis and latest_analysis.evidence_json:
        evidence_samples = _build_evidence_samples(
            db, profile_id, profile.name, system_prompt, latest_analysis
        )
        results.extend(evidence_samples)
        logger.info(
            f"SFT export: added {len(evidence_samples)} evidence-backed samples "
            f"for profile {profile_id}"
        )

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

    # Add metadata about evidence if available
    metadata_note = ""
    if latest_analysis and latest_analysis.evidence_json:
        try:
            ev = json.loads(latest_analysis.evidence_json)
            total_claims = sum(
                len(mod.get("claims", []))
                for mod in ev.values()
                if isinstance(mod, dict)
            )
            metadata_note = f"（含 {total_claims} 条证据判断）"
        except Exception:
            pass
    if metadata_note:
        results.insert(0, {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{profile.name}的人物分析有多少证据支持？"},
                {"role": "assistant", "content": f"最新的人物分析基于 {latest_analysis.total_chunks} 个文本片段的资料生成，使用了 {latest_analysis.model_used} 模型分析。{metadata_note}"},
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
