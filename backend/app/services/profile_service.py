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

    for i, chunk_content in enumerate(unique_chunks):
        chunk = Chunk(
            document_id=doc.id,
            profile_id=profile_id,
            chunk_index=i,
            content=chunk_content,
            char_count=len(chunk_content),
        )
        db.add(chunk)

    db.commit()
    logger.info(f"Processed document '{filename}' for profile {profile_id}: {len(unique_chunks)} chunks stored")

    return {
        "document_id": doc.id,
        "filename": filename,
        "chunk_count": len(unique_chunks),
        "char_count": len(cleaned),
    }


# ── Analysis Report Generation ──

async def generate_analysis_report(
    db: Session,
    profile_id: int,
) -> AnalysisReport:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    chunks = db.query(Chunk).filter(Chunk.profile_id == profile_id).order_by(Chunk.chunk_index).all()
    if not chunks:
        raise ValueError("该人物没有任何资料，请先上传资料。")

    total_chunks = len(chunks)
    total_chars = sum(c.char_count for c in chunks)

    # Pick representative chunks: first N + sampled from middle/end
    MAX_CONTEXT_CHARS = 30000
    context_parts = []
    current_len = 0
    for chunk in chunks:
        if current_len + len(chunk.content) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(chunk.content)
        current_len += len(chunk.content)

    full_context = "\n\n---\n\n".join(context_parts)
    rel_type = profile.relationship_type or "other"

    # Get template for this relationship type
    template = get_template(rel_type)

    llm = get_llm_provider()

    # Step 1: Generate deep portrait report (Markdown output directly)
    analysis_prompt = template.analysis_system_prompt
    portrait_md = ""
    try:
        portrait_raw = await llm.generate_analysis(
            system_prompt=analysis_prompt,
            user_prompt=(
                f"请分析以下关于 {profile.name} 的资料（关系类型：{rel_type}），"
                f"共计 {total_chunks} 条片段、{total_chars} 字符，生成深度人物分析报告。\n\n"
                f"{full_context}"
            ),
            temperature=0.5,
            max_tokens=4096,
        )
        # The LLM now outputs Markdown directly; clean and add compliance header
        portrait_md = _clean_portrait_md(profile.name, portrait_raw, total_chunks, total_chars)
    except LLMError as e:
        logger.error(f"LLM analysis failed: {e}")
        portrait_md = _fallback_portrait(profile.name, total_chunks, total_chars, str(e))
    except Exception as e:
        logger.warning(f"Failed to generate portrait: {e}")
        if 'portrait_raw' in dir():
            portrait_md = _clean_portrait_md(profile.name, portrait_raw, total_chunks, total_chars)
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

    # Local retrieval
    all_chunks = (
        db.query(Chunk)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )
    chunk_texts = [c.content for c in all_chunks]
    relevant_chunks = search_chunks_local(user_message, chunk_texts, top_k=5)
    retrieved_context = (
        "\n\n---\n\n".join([c["content"] for c in relevant_chunks])
        if relevant_chunks else "（尚无相关资料）"
    )

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
        "retrieved_context": retrieved_context,
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
            [c["content"][:200] for c in relevant_chunks], ensure_ascii=False,
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
        "model_used": llm.model_name,
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
