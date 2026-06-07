from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.database import Profile, Document, Chunk, AnalysisReport, ChatMessage
from app.services.llm_provider import get_llm_provider, LLMError
from app.services.document_processor import (
    clean_text, chunk_text, deduplicate_chunks,
    search_chunks_local,
)
from app.skill_templates import get_template, safe_format_template
from app.skill_templates.base import CHAT_MODE_INSTRUCTIONS, COMPLIANCE_STATEMENT
from app.core.config import get_settings

logger = logging.getLogger(__name__)

COMPLIANCE_DISCLAIMER = (
    "[重要声明] 这是一个基于用户上传资料由 AI 生成的模拟角色，并非本人意识，"
    "不代表本人真实意愿。禁止用于冒充真人、诈骗、骚扰、伪造授权、伪造遗嘱、"
    "法律/医疗/财务决定等违法用途。上传他人资料前应确保已获得合法授权。"
)

# ── Data Sufficiency ──

def get_data_sufficiency(total_chars: int, chunk_count: int) -> dict:
    """Determine data sufficiency level based on character count and chunks."""
    if total_chars == 0:
        level = "none"
        label = "无资料"
        description = "尚未上传任何资料，无法进行分析或模拟。请先上传文本资料。"
        sim_suitable = False
    elif total_chars <= 2000:
        level = "very_low"
        label = "资料极少"
        description = "资料非常有限，只能做粗略推断，语气模拟不稳定。建议上传更多资料（至少 2000 字以上）。"
        sim_suitable = False
    elif total_chars <= 10000:
        level = "low"
        label = "基础画像"
        description = "资料量可生成基础画像，语言风格和性格倾向有一定参考价值，但深层分析可能不够稳定。"
        sim_suitable = False
    elif total_chars <= 50000:
        level = "medium"
        label = "中等可靠"
        description = "资料较充足，可做较稳定的风格分析和语气模拟，画像报告各模块可靠性较高。"
        sim_suitable = True
    else:
        level = "high"
        label = "较适合风格模拟"
        description = "资料充足，各维度分析可靠性高，适合做深入的语气模拟和风格复刻。"
        sim_suitable = True

    return {
        "level": level,
        "label": label,
        "description": description,
        "sim_suitable": sim_suitable,
        "total_chars": total_chars,
        "chunk_count": chunk_count,
    }


# ── Document Upload ──

async def process_document_upload(
    db: Session,
    profile_id: int,
    filename: str,
    text: str,
    parser: str = "builtin",
    parsed_text_path: str | None = None,
    original_file_path: str | None = None,
    parse_status: str = "success",
    parse_error: str | None = None,
) -> dict:
    cleaned = clean_text(text)
    if not cleaned.strip():
        raise ValueError("文件内容为空，无法处理。")

    raw_chunks = chunk_text(cleaned)
    unique_chunks = deduplicate_chunks(raw_chunks)

    doc = Document(
        profile_id=profile_id,
        filename=filename,
        file_type=filename.split(".")[-1] if "." in filename else "unknown",
        content_type="text/plain",
        char_count=len(cleaned),
        chunk_count=len(unique_chunks),
        parser=parser,
        parsed_text_path=parsed_text_path,
        original_file_path=original_file_path,
        parse_status=parse_status,
        parse_error=parse_error,
    )
    db.add(doc)
    db.flush()

    stored_chunks: list[Chunk] = []
    for i, chunk_content in enumerate(unique_chunks):
        chunk = Chunk(
            document_id=doc.id,
            profile_id=profile_id,
            chunk_index=i,
            content=chunk_content,
            char_count=len(chunk_content),
            parser=parser,
        )
        db.add(chunk)
        stored_chunks.append(chunk)

    db.flush()
    db.commit()
    logger.info(f"Processed document '{filename}' for profile {profile_id}: {len(unique_chunks)} chunks stored")

    try:
        from app.integrations.vector_adapter import index_chunks

        vector_chunks = [
            {
                "chunk_id": chunk.id,
                "document_id": doc.id,
                "profile_id": profile_id,
                "filename": filename,
                "chunk_index": chunk.chunk_index,
                "parser": parser,
                "char_count": chunk.char_count,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else "",
                "content": chunk.content,
            }
            for chunk in stored_chunks
        ]
        result = index_chunks(profile_id, vector_chunks)
        if result.get("indexed"):
            logger.info("Vector indexed %s chunks for profile %s document %s", result["indexed"], profile_id, doc.id)
    except Exception as e:
        logger.warning("Vector indexing skipped for profile=%s document=%s: %s", profile_id, doc.id, e)

    return {
        "document_id": doc.id,
        "filename": filename,
        "chunk_count": len(unique_chunks),
        "char_count": len(cleaned),
    }


# ── Analysis Report Generation ──

def _parse_evidence_map(raw: str) -> str:
    """Extract evidence_map JSON from LLM response.
    Expects format: Markdown report followed by === then JSON evidence_map."""
    if not raw:
        return ""
    # Split on === (on its own line)
    parts = raw.split("\n===\n")
    if len(parts) < 2:
        # Try alternative: search for last JSON object
        import re
        # Find the last { } block that contains "module_name"
        matches = list(re.finditer(r'\{[^{}]*"module_name"[^{}]*\}', raw))
        if matches:
            # Not a full evidence_map, but partial
            pass
        return ""
    json_part = parts[-1].strip()
    # Strip code fences if present
    if json_part.startswith("```"):
        lines = json_part.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        json_part = "\n".join(lines).strip()
    try:
        parsed = json.loads(json_part)
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        logger.warning("Failed to parse evidence_map JSON from LLM response")
        return ""


def _portrait_md_from_raw(raw: str) -> str:
    """Extract the Markdown portrait from LLM response (before === separator)."""
    if not raw:
        return ""
    parts = raw.split("\n===\n")
    return parts[0].strip()


def _chunk_to_result(chunk: Chunk, filename: str = "", parser: str | None = None, score: float = 0.0) -> dict:
    return {
        "content": chunk.content,
        "score": score,
        "similarity_score": None,
        "retrieval_method": "keyword",
        "profile_id": chunk.profile_id,
        "document_id": chunk.document_id,
        "chunk_id": chunk.id,
        "filename": filename,
        "chunk_index": chunk.chunk_index,
        "parser": parser or chunk.parser or "builtin",
        "char_count": chunk.char_count,
    }


def _search_chunks_keyword(db: Session, profile_id: int, query: str, top_k: int) -> list[dict]:
    rows = (
        db.query(Chunk, Document.filename, Document.parser)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )
    if not rows:
        return []
    chunk_texts = [row[0].content for row in rows]
    scored = search_chunks_local(query, chunk_texts, top_k=top_k)
    by_content: dict[str, list[tuple[Chunk, str, str | None]]] = {}
    for chunk, filename, parser in rows:
        by_content.setdefault(chunk.content, []).append((chunk, filename, parser))

    results = []
    used_ids = set()
    for item in scored:
        candidates = by_content.get(item["content"], [])
        selected = next((c for c in candidates if c[0].id not in used_ids), None)
        if not selected:
            continue
        chunk, filename, parser = selected
        used_ids.add(chunk.id)
        results.append(_chunk_to_result(chunk, filename, parser, float(item.get("score", 0.0))))
    return results


def search_relevant_chunks(db: Session, profile_id: int, query: str, top_k: int | None = None) -> tuple[list[dict], str]:
    """Vector-first retrieval with keyword fallback."""
    limit = top_k or get_settings().vector_top_k
    try:
        from app.integrations.vector_adapter import search_chunks_vector

        vector_results = search_chunks_vector(profile_id, query, top_k=limit)
        if vector_results:
            return vector_results, "vector"
    except Exception as e:
        logger.warning("Vector search fallback for profile=%s: %s", profile_id, e)

    return _search_chunks_keyword(db, profile_id, query, top_k=limit), "keyword"


def _format_retrieved_context(chunks: list[dict], method: str) -> str:
    if not chunks:
        return "（尚无相关资料）"
    parts = []
    for c in chunks:
        score_label = ""
        if method == "vector" and c.get("similarity_score") is not None:
            score_label = f" [similarity={float(c['similarity_score']):.4f}]"
        parts.append(
            f"[chunk_id={c.get('chunk_id')}] [chunk_index={c.get('chunk_index')}] "
            f"[source={c.get('filename', '')}] [retrieval={method}]{score_label}\n"
            f"{c.get('content', '')}"
        )
    return "\n\n---\n\n".join(parts)


def _enrich_evidence_json(db: Session, profile_id: int, evidence_json: str) -> str:
    if not evidence_json:
        return evidence_json
    try:
        evidence_map = json.loads(evidence_json)
    except json.JSONDecodeError:
        return evidence_json

    chunk_rows = (
        db.query(Chunk, Document.filename, Document.parser)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )
    by_index: dict[int, tuple[Chunk, str, str | None]] = {}
    for chunk, filename, parser in chunk_rows:
        by_index.setdefault(chunk.chunk_index, (chunk, filename, parser))

    vector_available = False
    try:
        from app.integrations.vector_adapter import is_vector_available

        vector_available = is_vector_available()
    except Exception:
        vector_available = False

    for module in evidence_map.values():
        if not isinstance(module, dict):
            continue
        for claim in module.get("claims", []):
            if not isinstance(claim, dict):
                continue
            for item in claim.get("evidence", []):
                if not isinstance(item, dict):
                    continue
                idx = item.get("chunk_index")
                chunk_tuple = by_index.get(idx) if isinstance(idx, int) else None
                if chunk_tuple:
                    chunk, filename, parser = chunk_tuple
                    item.setdefault("chunk_id", chunk.id)
                    item.setdefault("filename", filename)
                    item.setdefault("parser", parser or chunk.parser or "builtin")
                item["retrieval_method"] = "vector" if vector_available else "keyword"
                if vector_available and item.get("quote"):
                    try:
                        from app.integrations.vector_adapter import search_chunks_vector

                        hits = search_chunks_vector(profile_id, str(item["quote"]), top_k=1)
                        if hits:
                            item["similarity_score"] = round(float(hits[0].get("similarity_score", 0.0)), 4)
                    except Exception as e:
                        logger.debug("Evidence similarity skipped: %s", e)
                elif "similarity_score" not in item:
                    item["similarity_score"] = None

    return json.dumps(evidence_map, ensure_ascii=False)


async def generate_analysis_report(
    db: Session,
    profile_id: int,
) -> AnalysisReport:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    # Get all chunks with their document info for evidence context
    chunks_with_docs = (
        db.query(Chunk, Document.filename, Document.parser)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .order_by(Chunk.chunk_index)
        .all()
    )

    if not chunks_with_docs:
        raise ValueError("该人物没有任何资料，请先上传资料。")

    # Build chunks list with metadata
    all_chunks = []
    for chunk, filename, doc_parser in chunks_with_docs:
        all_chunks.append({
            "chunk_index": chunk.chunk_index,
            "chunk_id": chunk.id,
            "content": chunk.content,
            "char_count": chunk.char_count,
            "filename": filename,
            "parser": doc_parser or "builtin",
        })

    total_chunks = len(all_chunks)
    total_chars = sum(c["char_count"] for c in all_chunks)

    # Pick representative chunks. Vector retrieval is preferred when enabled;
    # keyword/chronological context remains the fallback.
    MAX_CONTEXT_CHARS = 30000
    context_parts = []
    context_with_indices = []
    current_len = 0
    context_source_chunks = all_chunks
    retrieval_method = "keyword"
    analysis_query = (
        f"{profile.name} {profile.description or ''} 人物摘要 语言风格 价值观 "
        "行为模式 冲突处理 证据化人物画像"
    )
    try:
        relevant, method = search_relevant_chunks(
            db,
            profile_id,
            analysis_query,
            top_k=max(6, min(get_settings().vector_top_k, 10)),
        )
        if relevant and method == "vector":
            retrieval_method = method
            context_source_chunks = relevant
    except Exception as e:
        logger.warning("Analysis vector context fallback for profile=%s: %s", profile_id, e)

    for c in context_source_chunks:
        if current_len + len(c["content"]) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(c["content"])
        score_label = ""
        if c.get("retrieval_method") == "vector" and c.get("similarity_score") is not None:
            score_label = f" [similarity={float(c['similarity_score']):.4f}]"
        context_with_indices.append(
            f"[chunk_id={c.get('chunk_id')}] [chunk_index={c['chunk_index']}] "
            f"[source={c['filename']}] [retrieval={c.get('retrieval_method', retrieval_method)}]{score_label} "
            f"{c['content']}"
        )
        current_len += len(c["content"])

    full_context = "\n\n---\n\n".join(context_with_indices)
    rel_type = profile.relationship_type or "other"

    # Get template for this relationship type
    template = get_template(rel_type)

    llm = get_llm_provider()

    # Step 1: Generate deep portrait report with evidence_map
    analysis_prompt = template.analysis_system_prompt
    portrait_md = ""
    evidence_json = ""
    try:
        portrait_raw = await llm.generate_analysis(
            system_prompt=analysis_prompt,
            user_prompt=(
                f"请分析以下关于 {profile.name} 的资料（关系类型：{rel_type}），"
                f"共计 {total_chunks} 条片段、{total_chars} 字符，生成深度人物分析报告和 evidence_map。\n\n"
                f"注意：每条资料都以 [chunk_index=N] [source=文件名] 开头，"
                f"请在 evidence_map 中引用准确的 chunk_index。\n\n"
                f"当前证据上下文检索方式：{retrieval_method}。如果为 vector，资料片段来自语义检索，"
                f"请优先参考 similarity 较高且内容具体的片段。\n\n"
                f"{full_context}"
            ),
            temperature=0.5,
            max_tokens=8192,
        )
        # Split portrait and evidence_map
        portrait_md = _portrait_md_from_raw(portrait_raw)
        if not portrait_md:
            portrait_md = portrait_raw  # Fallback if no === separator
        evidence_json = _parse_evidence_map(portrait_raw)
        evidence_json = _enrich_evidence_json(db, profile_id, evidence_json)
        # Clean and add compliance header
        portrait_md = _clean_portrait_md(profile.name, portrait_md, total_chunks, total_chars)
    except LLMError as e:
        logger.error(f"LLM analysis failed: {e}")
        portrait_md = _fallback_portrait(profile.name, total_chunks, total_chars, str(e))
    except Exception as e:
        logger.warning(f"Failed to generate portrait: {e}")
        if 'portrait_raw' in dir() and portrait_raw:
            parts = portrait_raw.split("\n===\n")
            portrait_md = _clean_portrait_md(profile.name, parts[0].strip(), total_chunks, total_chars)
            evidence_json = _parse_evidence_map(portrait_raw)
            evidence_json = _enrich_evidence_json(db, profile_id, evidence_json)
        else:
            portrait_md = _fallback_portrait(profile.name, total_chunks, total_chars, str(e))

    # Step 2: Generate style card using template's style card prompt
    style_card_prompt = template.style_card_system_prompt
    try:
        style_card = await llm.generate_analysis(
            system_prompt=style_card_prompt,
            user_prompt=(
                f"请基于以下关于 {profile.name} 的资料（关系类型：{rel_type}），"
                f"共计 {total_chunks} 条片段、{total_chars} 字符，生成人物风格卡。\n\n"
                f"{full_context}"
            ),
            temperature=0.5,
            max_tokens=4096,
        )
        style_card = style_card.replace("[人物名]", profile.name)
    except LLMError as e:
        logger.error(f"LLM style card failed: {e}")
        style_card = _fallback_style_card(profile.name, total_chunks, total_chars, str(e))
    except Exception as e:
        logger.error(f"Failed to generate style card: {e}")
        style_card = _fallback_style_card(profile.name, total_chunks, total_chars, str(e))

    report = AnalysisReport(
        profile_id=profile_id,
        portrait_report=portrait_md,
        style_card=style_card,
        evidence_json=evidence_json,
        total_chunks=total_chunks,
        total_chars=total_chars,
        model_used=llm.model_name,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return report


def _clean_portrait_md(name: str, raw: str, total_chunks: int, total_chars: int) -> str:
    """Clean the LLM Markdown output and prepend compliance header."""
    # Remove any leading/trailing whitespace and code fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # If the LLM already produced a full report starting with #, use as-is
    # with compliance header prepended
    header = (
        f"> {COMPLIANCE_DISCLAIMER}\n\n"
        f"> 资料统计：{total_chunks} 条片段 · {total_chars} 字符\n\n"
        "---\n\n"
    )
    return header + text


def _fallback_portrait(name: str, total_chunks: int, total_chars: int, error_msg: str = "") -> str:
    parts = [
        f"# {name} 的深度人物分析报告",
        "",
        f"> {COMPLIANCE_DISCLAIMER}",
        "",
        "## 1. 人物摘要",
        "画像生成遇到问题，请重试。",
        "",
        "## 2. 资料覆盖范围",
        f"已上传 {total_chunks} 条片段，共 {total_chars} 字符。",
        "",
        "## 14. 合规声明",
        "- 这是 AI 基于资料生成的模拟角色，不是本人意识",
        "- 不代表本人真实意愿",
        "- 禁止冒充真人、诈骗、骚扰、伪造授权、伪造遗嘱、法律/医疗/财务决定",
    ]
    if error_msg:
        parts += ["", f"## 错误详情", error_msg]
    return "\n".join(parts)


def _fallback_style_card(name: str, total_chunks: int, total_chars: int, error_msg: str = "") -> str:
    parts = [
        f"# {name} 的 AI 风格卡",
        "",
        "## 1. 角色定位",
        f"这是基于 {total_chunks} 条资料片段生成的 AI 模拟角色，不代表本人。",
        "",
        "## 2. 资料来源摘要",
        f"已分析 {total_chunks} 条片段，共 {total_chars} 字符。",
        "",
        "## 9. 禁止模仿的部分",
        "- 不得声称自己就是本人",
        "- 不得代表本人作出承诺、授权或同意",
        "- 不得生成欺骗性内容",
    ]
    if error_msg:
        parts += ["", f"> 风格卡生成失败：{error_msg}"]
    return "\n".join(parts)


# ── Chat ──

async def chat_with_profile(
    db: Session,
    profile_id: int,
    user_message: str,
    mode: str = "daily_chat",
) -> dict:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    latest_analysis = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )

    has_chunks = db.query(Chunk).filter(Chunk.profile_id == profile_id).count() > 0
    rel_type = profile.relationship_type or "other"
    template = get_template(rel_type)

    if latest_analysis and latest_analysis.style_card:
        style_card = latest_analysis.style_card
    else:
        total_chars = sum(c.char_count for c in db.query(Chunk).filter(Chunk.profile_id == profile_id).all()) if has_chunks else 0
        chunk_count = db.query(Chunk).filter(Chunk.profile_id == profile_id).count()
        style_card = safe_format_template(DEFAULT_STYLE_CARD, {
            "name": profile.name,
            "has_data": "已上传资料，但尚未生成画像" if has_chunks else "尚无资料",
            "total_chars": str(total_chars),
            "chunk_count": str(chunk_count),
        })

    all_chunks = db.query(Chunk).filter(Chunk.profile_id == profile_id).all()
    chunk_texts = [c.content for c in all_chunks]
    relevant_chunks, retrieval_method = search_relevant_chunks(
        db,
        profile_id,
        user_message,
        top_k=max(6, min(get_settings().vector_top_k, 10)),
    )
    retrieved_context = _format_retrieved_context(relevant_chunks, retrieval_method)

    # mem0 long-term memory (optional, silent fallback — never breaks chat)
    mem0_context = ""
    try:
        from app.integrations.mem0_adapter import search_memory_sync
        mem0_results = search_memory_sync(f"profile_{profile_id}", user_message, limit=3)
        if mem0_results:
            mem0_context = "长期记忆：\n" + "\n".join(
                m.get("memory", "") for m in mem0_results if m.get("memory")
            )
            retrieved_context = mem0_context + "\n\n" + retrieved_context
            logger.debug("mem0: retrieved %d memories for profile %d", len(mem0_results), profile_id)
    except Exception as e:
        logger.debug("mem0 search skipped (profile %d): %s", profile_id, e)

    # Total chars for context
    total_chars = sum(len(c) for c in chunk_texts)

    # Get mode instruction
    mode_instruction = CHAT_MODE_INSTRUCTIONS.get(mode, CHAT_MODE_INSTRUCTIONS["daily_chat"])

    # Build system prompt
    chat_template = template.chat_system_template
    if not chat_template:
        chat_template = DEFAULT_CHAT_TEMPLATE

    system_prompt = safe_format_template(chat_template, {
        "style_card": style_card,
        "retrieved_context": (
            f"当前检索方式：{retrieval_method}。"
            f"{'这些片段来自语义向量检索，请优先参考高 similarity 片段。' if retrieval_method == 'vector' else '当前使用关键词检索 fallback。'}\n\n"
            f"{retrieved_context}"
        ),
        "user_message": user_message,
        "mode_instruction": mode_instruction,
    })

    llm = get_llm_provider()

    try:
        reply = await llm.generate_chat_reply(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.8,
            max_tokens=2048,
        )
    except LLMError as e:
        logger.error(f"Chat LLM error: {e}")
        reply = f"抱歉，AI 回复生成失败：{e}。请检查 LLM Provider 配置或稍后重试。"

    # Store messages
    user_msg = ChatMessage(profile_id=profile_id, role="user", content=user_message)
    db.add(user_msg)
    assistant_msg = ChatMessage(
        profile_id=profile_id,
        role="assistant",
        content=reply,
        retrieved_chunks=json.dumps(
            [
                {
                    "chunk_id": c.get("chunk_id"),
                    "chunk_index": c.get("chunk_index"),
                    "filename": c.get("filename", ""),
                    "content": c.get("content", "")[:300],
                    "retrieval_method": c.get("retrieval_method", retrieval_method),
                    "similarity_score": c.get("similarity_score"),
                    "score": c.get("score"),
                }
                for c in relevant_chunks
            ],
            ensure_ascii=False,
        ),
    )
    db.add(assistant_msg)
    db.commit()

    # Store to mem0 long-term memory (optional, silent fallback — never breaks chat)
    try:
        from app.integrations.mem0_adapter import add_memory_sync
        add_memory_sync(
            f"profile_{profile_id}",
            f"用户问: {user_message[:500]}",
            metadata={"type": "chat", "role": "user", "mode": mode},
        )
        add_memory_sync(
            f"profile_{profile_id}",
            f"AI回复: {reply[:500]}",
            metadata={"type": "chat", "role": "assistant", "profile_name": profile.name, "mode": mode},
        )
        logger.debug("mem0: stored 2 memories for profile %d mode=%s", profile_id, mode)
    except Exception as e:
        logger.debug("mem0 store skipped (profile %d): %s", profile_id, e)

    return {
        "reply": reply,
        "retrieved_count": len(relevant_chunks),
        "retrieval_method": retrieval_method,
        "retrieved_chunks": [
            {
                "chunk_id": c.get("chunk_id"),
                "chunk_index": c.get("chunk_index"),
                "filename": c.get("filename", ""),
                "content": c.get("content", "")[:300],
                "retrieval_method": c.get("retrieval_method", retrieval_method),
                "similarity_score": c.get("similarity_score"),
                "score": c.get("score"),
            }
            for c in relevant_chunks
        ],
        "model_used": llm.model_name,
    }


# ── Analysis Quality ──

def calculate_analysis_quality(db: Session, profile_id: int) -> dict:
    """Calculate comprehensive analysis quality metrics."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return {}

    all_chunks = (
        db.query(Chunk, Document.filename, Document.parser, Document.file_type)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )

    chunk_count = len(all_chunks)
    doc_count = db.query(Document).filter(Document.profile_id == profile_id).count()
    total_chars = sum(c[0].char_count for c in all_chunks) if all_chunks else 0
    filenames = set(c[1] for c in all_chunks)
    parsers = set(c[2] for c in all_chunks)
    file_types = set(c[3] for c in all_chunks)

    # Check latest analysis for evidence coverage
    latest = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )

    evidence_coverage = 0.0
    avg_confidence = 0.0
    if latest and latest.evidence_json:
        try:
            ev = json.loads(latest.evidence_json)
            total_claims = 0
            total_conf = 0
            modules_with_data = 0
            for mod_key, mod_data in ev.items():
                if isinstance(mod_data, dict):
                    claims = mod_data.get("claims", [])
                    if mod_data.get("data_sufficient", False) and claims:
                        modules_with_data += 1
                    for claim in claims:
                        if isinstance(claim, dict):
                            total_claims += 1
                            total_conf += claim.get("confidence_score", 0)
            if 14 > 0:
                evidence_coverage = round(modules_with_data / 14 * 100, 1)
            if total_claims > 0:
                avg_confidence = round(total_conf / total_claims, 1)
        except (json.JSONDecodeError, Exception):
            pass

    # Diversity scoring
    diversity_score = 0.0
    if doc_count > 0:
        diversity_score += min(doc_count * 10, 30)  # Up to 30 for doc count
        if len(file_types) > 1:
            diversity_score += min(len(file_types) * 10, 20)  # Up to 20 for file type variety
        if "mineru" in parsers:
            diversity_score += 15  # Bonus for complex doc parsing
    diversity_score = min(diversity_score, 100)

    # Check content types
    all_text = " ".join(c[0].content[:500] for c in all_chunks[:50]).lower()
    has_chat_corpus = any(kw in all_text for kw in ["聊天", "对话", "我说", "他说", "回复", "消息", "微信", "qq", "短信"])
    has_long_text = any(c[0].char_count > 800 for c in all_chunks)
    has_multi_emotion = any(kw in all_text for kw in ["开心", "难过", "生气", "焦虑", "兴奋", "失望", "愤怒", "高兴", "哭"])

    # Suitability level
    if total_chars < 2000:
        suitability_level = "rough"
        suitability_label = "粗略画像"
    elif total_chars < 10000:
        suitability_level = "basic"
        suitability_label = "基础画像"
    elif total_chars < 50000 and evidence_coverage < 40:
        suitability_level = "moderate"
        suitability_label = "中等可靠"
    elif total_chars >= 50000 and evidence_coverage >= 40:
        suitability_level = "style_sim"
        suitability_label = "较适合风格模拟"
    elif total_chars >= 50000 and evidence_coverage >= 60:
        suitability_level = "personality_replica"
        suitability_label = "可用于人格分析参考"
    else:
        suitability_level = "moderate"
        suitability_label = "中等可靠"
    # Don't over-claim
    if suitability_level == "personality_replica" and not has_chat_corpus:
        suitability_level = "style_sim"
        suitability_label = "较适合风格模拟（仍不足以人格复刻）"

    return {
        "total_chars": total_chars,
        "document_count": doc_count,
        "chunk_count": chunk_count,
        "evidence_coverage": evidence_coverage,
        "avg_confidence": avg_confidence,
        "diversity_score": round(diversity_score, 1),
        "has_chat_corpus": has_chat_corpus,
        "has_long_text": has_long_text,
        "has_multi_emotion": has_multi_emotion,
        "suitability_level": suitability_level,
        "suitability_label": suitability_label,
        "distinct_sources": len(filenames),
        "parsers": list(parsers),
    }


# ── Export ──

def export_skill_card(db: Session, profile_id: int) -> str:
    """Export a profile's analysis as a Skill Card Markdown file."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    latest = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )

    if not latest:
        raise ValueError("该人物尚未生成画像，请先上传资料并运行分析。")

    rel_type = profile.relationship_type or "other"

    skill_md_name = profile.name.replace(" ", "_")
    parts = [
        f"# {skill_md_name}.skill.md",
        "",
        f"name: {skill_md_name}",
        f"target_type: {rel_type}",
        f"description: AI Clone 自动生成的人物风格卡，基于 {latest.total_chunks} 个文本片段（{latest.total_chars} 字符）分析生成",
        f"model: {latest.model_used}",
        f"generated_at: {latest.created_at.isoformat() if latest.created_at else 'unknown'}",
        f"source: AI Clone (ai-clone)",
        "",
        "> 此 SKILL.md 文件由 AI Clone 自动生成，可被 Claude Code / Codex / Cursor 等工具读取作为人物风格说明。",
        "> 这是基于资料的 AI 模拟角色，不代表本人真实意愿。",
        "",
        "---",
        "",
        "## 深度人物分析报告",
        "",
        latest.portrait_report or "（无）",
        "",
        "---",
        "",
        "## AI 风格卡",
        "",
        latest.style_card or "（无）",
        "",
        "---",
        "",
        "## 合规声明",
        "",
        f"- {COMPLIANCE_DISCLAIMER}",
        "- 本 SKILL.md 供了解人物风格、辅助工具使用，不得用于冒充、诈骗等违法用途。",
        "- 如涉及他人隐私，请确保已获合法授权。",
    ]

    return "\n".join(parts)


# ── Default Templates ──

DEFAULT_STYLE_CARD = """# {name} 的 AI 风格卡（默认）

## 1. 角色定位
这是 AI 模拟角色，尚未基于真实资料生成风格卡。当前使用默认风格对话。

## 2. 资料来源摘要
- {has_data}
- 资料量：{total_chars} 字符 · {chunk_count} 片段

## 3. 语言模仿规则
- 尚无足够资料分析语言风格
- 默认使用自然、友好的中文表达

## 4. 思考方式
- 尚无足够资料分析思考偏好

## 8. 回答问题时的优先级
- 默认先共情、再分析
- 保持友好、有帮助的对话态度

## 9. 禁止模仿的部分
- 此为 AI 模拟角色，不得冒充真人
- 禁止用于诈骗、骚扰、伪造授权、伪造遗嘱、法律/医疗/财务决定

## 10. Prompt 使用建议
- 请先上传资料（文章、聊天记录、笔记等），然后运行分析生成真实的风格卡
- 资料不足时，按"根据已有资料，只能大致判断……"的方式诚实回答
"""

DEFAULT_CHAT_TEMPLATE = """你正在模拟一个基于资料生成的 AI 角色。

{style_card}

你必须遵守以下核心规则：
1. 你是 AI 模拟角色，不是真人。绝对不要声称自己是真人或有自我意识。
2. 模拟的是语气、表达方式、思考倾向，不是声称自己有本人的记忆或经历。
3. 根据风格卡和检索到的资料来回答，优先依据资料内容。
4. 如果资料中没有相关信息，自然地说"根据目前资料，我只能大致判断……"，切勿编造。
5. 使用风格卡中描述的表达方式，但要自然，不要刻意夸张模仿。
6. 当用户要求冒充真人、联系他人、生成欺骗内容、伪造授权/签名/遗嘱、或涉及法律/医疗/财务决定时，必须坚决拒绝并说明边界。
7. 不要机械重复合规声明，除非用户要求冒充、欺骗、伪造、骚扰或法律/医疗/财务决定。
8. 禁止输出 JSON，只输出纯文本。
9. 回复长度默认控制在 80 到 250 字，除非用户明确要求详细分析。
10. 回答必须是自然聊天语气，不要每次都像分析报告。

检索到的相关资料：
{retrieved_context}

用户消息：{user_message}

{mode_instruction}

请以模拟角色的方式自然回复（纯文本，不要输出 JSON）："""


# ── Export Analysis Report ──

def export_analysis_report(db: Session, profile_id: int) -> str:
    """Export the full analysis report including portrait, style card, evidence chain,
    confidence scores, data gaps, and compliance statement."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    latest = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    if not latest:
        raise ValueError("该人物尚未生成画像，请先上传资料并运行分析。")

    quality = calculate_analysis_quality(db, profile_id)

    parts = [
        f"# {profile.name} 的完整分析报告",
        "",
        f"> 生成时间：{latest.created_at.isoformat() if latest.created_at else '未知'}",
        f"> 分析模型：{latest.model_used}",
        f"> 资料统计：{latest.total_chunks} 条片段 · {latest.total_chars} 字符",
        f"> 证据覆盖率：{quality.get('evidence_coverage', 0)}%",
        f"> 平均置信度：{quality.get('avg_confidence', 0)}",
        f"> 适合程度：{quality.get('suitability_label', '未知')}",
        "",
        "---",
        "",
        "## 深度人物画像",
        "",
        latest.portrait_report or "（无）",
        "",
        "---",
        "",
        "## AI 风格卡",
        "",
        latest.style_card or "（无）",
        "",
        "---",
        "",
        "## 证据链",
        "",
    ]

    if latest.evidence_json:
        try:
            ev = json.loads(latest.evidence_json)
            for mod_key in sorted(ev.keys(), key=lambda k: int(k) if k.isdigit() else 99):
                mod = ev[mod_key]
                if isinstance(mod, dict):
                    module_name = mod.get("module_name", f"模块 {mod_key}")
                    parts.append(f"### 模块 {mod_key}：{module_name}")
                    if not mod.get("data_sufficient", True):
                        parts.append("**资料不足，无法提供可靠证据。**")
                        parts.append("")
                        continue
                    for i, claim in enumerate(mod.get("claims", [])):
                        if isinstance(claim, dict):
                            parts.append(f"#### 判断 {i+1}: {claim.get('claim', '')}")
                            parts.append(f"- 置信度：{claim.get('confidence_score', 0)}/100")
                            for ev_item in claim.get("evidence", []):
                                if isinstance(ev_item, dict):
                                    parts.append(
                                        f"  - 证据（chunk_index={ev_item.get('chunk_index', '?')}）："
                                        f"> {ev_item.get('quote', '')}"
                                    )
                            if claim.get("data_gap"):
                                parts.append(f"- 资料不足项：{claim['data_gap']}")
                            if claim.get("contradiction"):
                                parts.append(f"- 矛盾表达：{claim['contradiction']}")
                            parts.append("")
        except (json.JSONDecodeError, Exception):
            parts.append("证据地图解析失败。")
    else:
        parts.append("当前分析未生成证据地图。请重新分析以生成 evidence_map。")

    parts += [
        "---",
        "",
        "## 资料不足项总览",
        "",
    ]

    # Extract all data_gaps from evidence
    if latest.evidence_json:
        try:
            ev = json.loads(latest.evidence_json)
            all_gaps = []
            for mod_key, mod in ev.items():
                if isinstance(mod, dict):
                    for claim in mod.get("claims", []):
                        if isinstance(claim, dict) and claim.get("data_gap"):
                            all_gaps.append(
                                f"- [{mod.get('module_name', mod_key)}] {claim['data_gap']}"
                            )
            if all_gaps:
                parts.append("\n".join(all_gaps))
            else:
                parts.append("所有模块资料充足，无明显缺失。")
        except Exception:
            parts.append("无法解析资料不足项。")
    else:
        parts.append("需要重新分析以获取资料不足项。")

    parts += [
        "",
        "---",
        "",
        "## 分析质量总览",
        f"- 资料字数：{quality.get('total_chars', 0):,}",
        f"- 文档数量：{quality.get('document_count', 0)}",
        f"- 片段数量：{quality.get('chunk_count', 0)}",
        f"- 来源文件数：{quality.get('distinct_sources', 0)}",
        f"- 证据覆盖率：{quality.get('evidence_coverage', 0)}%",
        f"- 平均置信度：{quality.get('avg_confidence', 0)}",
        f"- 资料多样性评分：{quality.get('diversity_score', 0)}/100",
        f"- 包含聊天语料：{'是' if quality.get('has_chat_corpus') else '否'}",
        f"- 包含长文本：{'是' if quality.get('has_long_text') else '否'}",
        f"- 包含多情绪场景：{'是' if quality.get('has_multi_emotion') else '否'}",
        f"- 当前适合程度：{quality.get('suitability_label', '未知')}",
        "",
        "---",
        "",
        "## 合规声明",
        "",
        f"- {COMPLIANCE_DISCLAIMER}",
        "- 本报告由 AI Clone 自动生成，仅供了解人物风格、辅助工具使用，不得用于冒充、诈骗等违法用途。",
        "- 分析结论为基于资料的 AI 推断，不代表事实或医学诊断。",
        "- 如涉及他人隐私，请确保已获合法授权。",
        "- 沟通策略仅用于良性沟通，不提供操控、PUA、骚扰、冒充真人策略。",
    ]

    return "\n".join(parts)
