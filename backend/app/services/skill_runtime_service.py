from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.database import (
    AnalysisReport,
    GeneratedSkill,
    Profile,
    SkillRuntimeFeedback,
    SkillRuntimeRun,
)
from app.services.llm_provider import LLMError, get_llm_provider
from app.services.profile_service import search_relevant_chunks

logger = logging.getLogger(__name__)

VALID_RUNTIME_MODES = {
    "nuwa_thinking",
    "colleague_interaction",
    "compare",
    "evidence_check",
    "uncertainty_check",
}

NUWA_FILES = [
    "SKILL.md",
    "persona.md",
    "thinking_framework.md",
    "decision_heuristics.md",
    "expression_dna.md",
    "evidence_map.md",
    "source_manifest.json",
]

COLLEAGUE_FILES = [
    "SKILL.md",
    "persona.md",
    "work.md",
    "persona_skill.md",
    "work_skill.md",
    "evidence_map.md",
    "source_manifest.json",
]

CORRECTION_RATINGS = {"inaccurate", "not_like_person", "missing_evidence"}
MAX_SKILL_FILE_CHARS = 7000
MAX_TOTAL_SKILL_CHARS = 26000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _safe_read(path: Path, max_chars: int = MAX_SKILL_FILE_CHARS) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Failed to read skill file %s: %s", path, exc)
        return ""
    return text[:max_chars] + ("\n\n[truncated]" if len(text) > max_chars else "")


def _expected_files(skill_type: str) -> list[str]:
    return NUWA_FILES if skill_type == "nuwa" else COLLEAGUE_FILES


def _read_skill_package(skill_path: str, skill_type: str) -> tuple[list[dict[str, str]], list[str], list[str]]:
    base = Path(skill_path)
    contexts: list[dict[str, str]] = []
    files_used: list[str] = []
    missing: list[str] = []
    total = 0

    for filename in _expected_files(skill_type):
        target = base / filename
        if not target.exists():
            missing.append(filename)
            continue
        remaining = max(MAX_TOTAL_SKILL_CHARS - total, 0)
        if remaining <= 0:
            break
        text = _safe_read(target, min(MAX_SKILL_FILE_CHARS, remaining))
        if not text:
            missing.append(filename)
            continue
        contexts.append({"filename": filename, "content": text})
        files_used.append(filename)
        total += len(text)

    return contexts, files_used, missing


def _mode_instruction(runtime_mode: str, skill_type: str) -> str:
    instructions = {
        "nuwa_thinking": (
            "重点运行 Nuwa Skill 的心智模型、思考框架、决策启发式和表达 DNA。"
            "回答应展示此人物如何理解问题、权衡信息、承认证据不足。"
        ),
        "colleague_interaction": (
            "重点运行 Colleague Skill 的协作规则、工作流、互动边界和任务推进方式。"
            "回答应像工作场景中的协作建议，而不是泛泛聊天。"
        ),
        "compare": (
            "用于 Nuwa 与 Colleague 的对照运行。只输出当前 Skill 的角度，最终对照由系统汇总。"
        ),
        "evidence_check": (
            "重点检查回答是否有证据支撑。优先引用检索片段和 Skill evidence_map；"
            "没有证据时必须明确标注为推断或资料不足。"
        ),
        "uncertainty_check": (
            "重点检查不确定性表达。资料不足、证据冲突、风格无法判断时必须直说，"
            "不得用确定口吻补全未知事实。"
        ),
    }
    default = instructions["evidence_check"]
    return instructions.get(runtime_mode, default) + f"\n当前 Skill type: {skill_type}."


def _safety_check(user_prompt: str) -> dict[str, Any]:
    text = user_prompt.lower()
    patterns = [
        ("impersonation", r"冒充|假装你是本人|假装是本人|代表本人|以.*本人.*名义|impersonate|pretend to be"),
        ("fraud", r"诈骗|骗|欺骗|伪造|fake|fraud|scam|forge|伪造签名|伪造授权|伪造遗嘱"),
        ("harassment", r"骚扰|威胁|恐吓|跟踪|harass|threaten|stalk"),
        ("manipulation", r"操控|控制他|控制她|pua|manipulate|洗脑|诱导对方"),
        ("high_stakes", r"法律意见|医疗建议|财务决定|投资建议|遗嘱|授权书|legal advice|medical advice|financial decision"),
    ]
    matches = []
    for category, pattern in patterns:
        if re.search(pattern, text, re.I):
            matches.append(category)
    return {
        "blocked": bool(matches),
        "risk_flags": sorted(set(matches)),
        "policy": (
            "Website Runtime 可用于站内测试 Skill 行为，但不能冒充真人、操控他人、骚扰、诈骗、"
            "伪造授权，或替代法律/医疗/财务等高风险决策。"
        ),
    }


def _blocked_answer(profile: Profile, safety: dict[str, Any]) -> str:
    flags = ", ".join(safety.get("risk_flags", [])) or "unsafe_request"
    return (
        f"我不能按这个请求运行 {profile.name} 的 Skill。检测到的风险类型：{flags}。\n\n"
        "这个站内 Runtime 只能用于基于资料的风格、思考框架和协作方式测试；"
        "不能声称自己就是本人，不能代表本人作出承诺、授权、同意或高风险决定，"
        "也不能用于操控、骚扰或欺骗他人。\n\n"
        "可以换成合规问题，例如：请基于证据说明此人物可能如何分析一个工作分歧，"
        "并列出哪些地方资料不足。"
    )


def _latest_evidence_items(db: Session, profile_id: int, limit: int = 8) -> list[dict[str, Any]]:
    latest = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    payload = _json_loads(latest.evidence_json if latest else "", {})
    if not isinstance(payload, dict):
        return []

    items: list[dict[str, Any]] = []
    for module_key in sorted(payload.keys(), key=lambda key: int(key) if str(key).isdigit() else 999):
        module = payload.get(module_key)
        if not isinstance(module, dict):
            continue
        module_name = module.get("module_name", f"module_{module_key}")
        for claim in module.get("claims", []):
            if not isinstance(claim, dict):
                continue
            for evidence in claim.get("evidence", [])[:2]:
                if not isinstance(evidence, dict):
                    continue
                items.append({
                    "type": "analysis_evidence",
                    "module": module_name,
                    "claim": claim.get("claim", ""),
                    "confidence_score": claim.get("confidence_score", 0),
                    "chunk_id": evidence.get("chunk_id", evidence.get("chunk_index")),
                    "filename": evidence.get("filename", ""),
                    "quote": str(evidence.get("quote", ""))[:900],
                    "retrieval_method": evidence.get("retrieval_method", "evidence_map"),
                    "similarity_score": evidence.get("similarity_score"),
                })
                if len(items) >= limit:
                    return items
    return items


def _retrieve_evidence(db: Session, profile_id: int, query: str, top_k: int = 8) -> tuple[list[dict[str, Any]], str]:
    chunks, method = search_relevant_chunks(db, profile_id, query, top_k=top_k)
    evidence = [
        {
            "type": "retrieved_chunk",
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "filename": chunk.get("filename", ""),
            "chunk_index": chunk.get("chunk_index"),
            "parser": chunk.get("parser", ""),
            "quote": str(chunk.get("content", ""))[:1000],
            "retrieval_method": chunk.get("retrieval_method", method),
            "similarity_score": chunk.get("similarity_score"),
            "score": chunk.get("score"),
        }
        for chunk in chunks[:top_k]
    ]
    existing_chunk_ids = {item.get("chunk_id") for item in evidence}
    for item in _latest_evidence_items(db, profile_id, limit=6):
        if item.get("chunk_id") in existing_chunk_ids and item.get("chunk_id") is not None:
            continue
        evidence.append(item)
        if len(evidence) >= top_k + 4:
            break
    return evidence, method


def _format_skill_context(skill_files: list[dict[str, str]]) -> str:
    if not skill_files:
        return "No readable Skill package files were found."
    return "\n\n".join(
        f"## FILE: {item['filename']}\n{item['content']}"
        for item in skill_files
    )


def _format_evidence_context(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "No profile evidence was retrieved."
    lines = []
    for idx, item in enumerate(evidence, start=1):
        score = ""
        if item.get("similarity_score") is not None:
            try:
                score = f", similarity={float(item['similarity_score']):.4f}"
            except (TypeError, ValueError):
                score = f", similarity={item.get('similarity_score')}"
        lines.append(
            f"[{idx}] type={item.get('type')}, chunk_id={item.get('chunk_id')}, "
            f"file={item.get('filename', '')}, retrieval={item.get('retrieval_method', '')}{score}\n"
            f"quote: {item.get('quote', '')}"
        )
        if item.get("claim"):
            lines.append(f"claim: {item.get('claim')}")
    return "\n\n".join(lines)


def _uncertainty_notes(skill_missing: list[str], evidence: list[dict[str, Any]], retrieval_method: str) -> list[str]:
    notes: list[str] = []
    if skill_missing:
        notes.append(f"Skill 包缺少文件：{', '.join(skill_missing)}")
    if not evidence:
        notes.append("没有检索到可用证据，回答只能进行保守说明。")
    if retrieval_method == "keyword":
        notes.append("当前证据检索使用关键词 fallback；语义向量检索未命中或不可用。")
    return notes


def _provider_label(llm: Any) -> str:
    provider = getattr(llm, "provider_name", "") or type(llm).__name__
    model = getattr(llm, "model_name", "")
    return f"{provider}/{model}" if model else provider


def _create_run(
    db: Session,
    profile_id: int,
    skill: GeneratedSkill,
    runtime_mode: str,
    user_prompt: str,
    answer: str,
    files_used: list[str],
    evidence_used: list[dict[str, Any]],
    runtime_trace: dict[str, Any],
    safety_check: dict[str, Any],
    model_provider: str,
    status: str,
    error: str | None = None,
) -> SkillRuntimeRun:
    row = SkillRuntimeRun(
        profile_id=profile_id,
        generated_skill_id=skill.id,
        skill_type=skill.skill_type,
        runtime_mode=runtime_mode,
        user_prompt=user_prompt,
        answer=answer,
        files_used_json=_json_dumps(files_used),
        evidence_used_json=_json_dumps(evidence_used),
        runtime_trace_json=_json_dumps(runtime_trace),
        safety_check_json=_json_dumps(safety_check),
        model_provider=model_provider,
        status=status,
        error=error,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def skill_runtime_run_to_dict(row: SkillRuntimeRun) -> dict[str, Any]:
    runtime_trace = _json_loads(row.runtime_trace_json, {})
    safety_check = _json_loads(row.safety_check_json, {})
    return {
        "id": row.id,
        "profile_id": row.profile_id,
        "generated_skill_id": row.generated_skill_id,
        "skill_type": row.skill_type,
        "runtime_mode": row.runtime_mode,
        "user_prompt": row.user_prompt or "",
        "answer": row.answer or "",
        "model_provider": row.model_provider or "",
        "files_used": _json_loads(row.files_used_json, []),
        "evidence_used": _json_loads(row.evidence_used_json, []),
        "uncertainty_notes": runtime_trace.get("uncertainty_notes", []),
        "safety_check": safety_check,
        "runtime_trace": runtime_trace,
        "status": row.status or "success",
        "error": row.error,
        "created_at": row.created_at,
    }


async def run_skill_in_website(
    db: Session,
    profile_id: int,
    skill_id: int,
    user_prompt: str,
    runtime_mode: str,
) -> dict[str, Any]:
    runtime_mode = runtime_mode if runtime_mode in VALID_RUNTIME_MODES else "evidence_check"
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    skill = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.id == skill_id, GeneratedSkill.profile_id == profile_id)
        .first()
    )
    if not skill:
        raise ValueError("生成的 Skill 不存在")

    skill_path = Path(skill.output_path or "")
    safety = _safety_check(user_prompt)
    trace: dict[str, Any] = {
        "website_runtime": True,
        "external_runtime_invoked": False,
        "l5c_marked": False,
        "runtime_mode": runtime_mode,
        "skill_type": skill.skill_type,
        "skill_path": str(skill_path),
        "created_at": _now().isoformat(),
    }

    if not skill.output_path or not skill_path.exists() or not skill_path.is_dir():
        error = "Skill 生成目录不存在，请重新生成 Skill 包。"
        trace["error"] = error
        row = _create_run(
            db, profile_id, skill, runtime_mode, user_prompt, error, [], [], trace, safety, "",
            status="error", error=error,
        )
        return skill_runtime_run_to_dict(row)

    skill_files, files_used, missing_files = _read_skill_package(str(skill_path), skill.skill_type)
    evidence_used, retrieval_method = _retrieve_evidence(db, profile_id, user_prompt, top_k=8)
    uncertainty = _uncertainty_notes(missing_files, evidence_used, retrieval_method)
    trace.update({
        "files_requested": _expected_files(skill.skill_type),
        "files_used": files_used,
        "missing_files": missing_files,
        "retrieval_method": retrieval_method,
        "evidence_count": len(evidence_used),
        "uncertainty_notes": uncertainty,
    })

    if safety.get("blocked"):
        answer = _blocked_answer(profile, safety)
        row = _create_run(
            db, profile_id, skill, runtime_mode, user_prompt, answer, files_used, evidence_used,
            trace, safety, "", status="blocked", error=None,
        )
        return skill_runtime_run_to_dict(row)

    system_prompt = (
        "你是 AI Clone 网站内置的 Website-native Skill Runtime。"
        "你会读取用户生成的 Persona Skill 包，并用当前网站配置的 LLM provider 执行一次站内测试。\n"
        "重要边界：本次运行不是 Codex / Claude Code / Hermes 外部 runtime，不得标记 L5c；"
        "不得声称自己就是真实本人；不得替本人作出承诺、授权、同意或高风险决定；"
        "不得用于操控、骚扰、诈骗或伪造。\n"
        "回答必须区分：资料事实、基于证据的推断、资料不足。"
        "如引用证据，请引用 chunk_id / filename / retrieval_method；"
        "如果证据来自 vector，应优先参考高 similarity 片段。"
    )
    user_payload = (
        f"# Profile\n"
        f"- name: {profile.name}\n"
        f"- relationship_type: {profile.relationship_type}\n"
        f"- description: {profile.description or ''}\n\n"
        f"# Runtime Mode\n{_mode_instruction(runtime_mode, skill.skill_type)}\n\n"
        f"# Skill Package Files\n{_format_skill_context(skill_files)}\n\n"
        f"# Retrieved Profile Evidence\n"
        f"retrieval_method={retrieval_method}\n"
        f"{_format_evidence_context(evidence_used)}\n\n"
        f"# User Prompt\n{user_prompt}\n\n"
        "请输出一个适合站内 Runtime Lab 展示的回答。结构建议：\n"
        "1. 回答\n2. 证据依据\n3. 不确定性/资料缺口\n4. 安全边界说明（如相关）。"
    )

    try:
        llm = get_llm_provider()
        model_provider = _provider_label(llm)
        answer = await llm.generate_analysis(
            system_prompt=system_prompt,
            user_prompt=user_payload,
            temperature=0.35,
            max_tokens=2600,
        )
        status = "success"
        error = None
    except (LLMError, Exception) as exc:
        model_provider = ""
        error = f"LLM provider 不可用：{exc}"
        answer = (
            "站内 Skill Runtime 未能调用当前 LLM provider。\n\n"
            f"{error}\n\n"
            "Skill 包和证据检索已经完成，但没有生成模型回答。请检查 LLM 配置后重试；"
            "这不会影响外部 runtime L5c 回填流程。"
        )
        status = "error"
        trace["llm_error"] = str(exc)

    row = _create_run(
        db, profile_id, skill, runtime_mode, user_prompt, answer, files_used, evidence_used,
        trace, safety, model_provider, status=status, error=error,
    )
    return skill_runtime_run_to_dict(row)


def list_skill_runtime_runs(db: Session, profile_id: int, skill_id: int, limit: int = 30) -> list[dict[str, Any]]:
    rows = (
        db.query(SkillRuntimeRun)
        .filter(SkillRuntimeRun.profile_id == profile_id, SkillRuntimeRun.generated_skill_id == skill_id)
        .order_by(SkillRuntimeRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [skill_runtime_run_to_dict(row) for row in rows]


def get_skill_runtime_run(db: Session, profile_id: int, skill_id: int, run_id: int) -> dict[str, Any]:
    row = (
        db.query(SkillRuntimeRun)
        .filter(
            SkillRuntimeRun.id == run_id,
            SkillRuntimeRun.profile_id == profile_id,
            SkillRuntimeRun.generated_skill_id == skill_id,
        )
        .first()
    )
    if not row:
        raise ValueError("站内 Skill Runtime 运行记录不存在")
    return skill_runtime_run_to_dict(row)


async def compare_skill_runs(
    db: Session,
    profile_id: int,
    nuwa_skill_id: int,
    colleague_skill_id: int,
    user_prompt: str,
) -> dict[str, Any]:
    nuwa = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.id == nuwa_skill_id, GeneratedSkill.profile_id == profile_id)
        .first()
    )
    colleague = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.id == colleague_skill_id, GeneratedSkill.profile_id == profile_id)
        .first()
    )
    if not nuwa or nuwa.skill_type != "nuwa":
        raise ValueError("Nuwa Skill 不存在或类型不匹配")
    if not colleague or colleague.skill_type != "colleague":
        raise ValueError("Colleague Skill 不存在或类型不匹配")

    nuwa_result = await run_skill_in_website(db, profile_id, nuwa_skill_id, user_prompt, "nuwa_thinking")
    colleague_result = await run_skill_in_website(db, profile_id, colleague_skill_id, user_prompt, "colleague_interaction")

    nuwa_evidence_count = len(nuwa_result.get("evidence_used", []))
    colleague_evidence_count = len(colleague_result.get("evidence_used", []))
    difference_table = [
        {
            "dimension": "thinking style",
            "nuwa": "偏心智模型、价值权衡、决策启发式。",
            "colleague": "偏协作语气、任务推进和工作流约束。",
        },
        {
            "dimension": "interaction rules",
            "nuwa": "更适合解释这个人物可能如何理解问题。",
            "colleague": "更适合模拟同事协作中的边界、节奏和行动建议。",
        },
        {
            "dimension": "evidence citation",
            "nuwa": f"使用 {nuwa_evidence_count} 条站内证据。",
            "colleague": f"使用 {colleague_evidence_count} 条站内证据。",
        },
        {
            "dimension": "uncertainty",
            "nuwa": "应主动标明资料事实、推断与未知。",
            "colleague": "应把资料不足转化为协作上的澄清问题。",
        },
        {
            "dimension": "suitable scenarios",
            "nuwa": "适合价值判断、思维复盘、表达 DNA 测试。",
            "colleague": "适合工作协作、冲突处理、任务推进话术。",
        },
    ]
    comparison_summary = (
        "Nuwa 与 Colleague 均为站内 Website Runtime 运行结果，不代表外部 runtime L5c。"
        "Nuwa 更强调内在思考框架，Colleague 更强调可协作的互动规则。"
    )
    if nuwa_result.get("status") == "error" or colleague_result.get("status") == "error":
        comparison_summary += " 本次至少一个 Skill 运行未能调用 LLM，请先查看错误信息。"
    recommendation = (
        "如果目标是理解人物如何思考，优先看 Nuwa；如果目标是与该人物风格一致地协作，优先看 Colleague。"
        "需要正式 L5c 时，仍需把 Skill 包安装到外部 runtime 后回填测试结果。"
    )
    return {
        "nuwa_result": nuwa_result,
        "colleague_result": colleague_result,
        "comparison_summary": comparison_summary,
        "difference_table": difference_table,
        "recommendation": recommendation,
    }


def submit_skill_runtime_feedback(
    db: Session,
    profile_id: int,
    skill_id: int,
    run_id: int,
    rating: str,
    note: str = "",
) -> dict[str, Any]:
    run = (
        db.query(SkillRuntimeRun)
        .filter(
            SkillRuntimeRun.id == run_id,
            SkillRuntimeRun.profile_id == profile_id,
            SkillRuntimeRun.generated_skill_id == skill_id,
        )
        .first()
    )
    if not run:
        raise ValueError("站内 Skill Runtime 运行记录不存在")

    skill = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.id == skill_id, GeneratedSkill.profile_id == profile_id)
        .first()
    )
    if not skill:
        raise ValueError("生成的 Skill 不存在")

    row = SkillRuntimeFeedback(
        run_id=run.id,
        profile_id=profile_id,
        generated_skill_id=skill_id,
        rating=rating,
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    appended = False
    if rating in CORRECTION_RATINGS:
        try:
            if not skill.output_path:
                raise ValueError("Skill output_path is empty")
            history_path = Path(skill.output_path) / "correction_history.md"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with history_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n\n"
                    f"## {_now().isoformat()}\n"
                    f"- run_id: {run.id}\n"
                    f"- rating: {rating}\n"
                    f"- note: {note or '（无补充说明）'}\n"
                )
            appended = True
        except Exception as exc:
            logger.warning("Failed to append correction_history.md for skill %s: %s", skill_id, exc)

    return {
        "id": row.id,
        "run_id": row.run_id,
        "profile_id": row.profile_id,
        "generated_skill_id": row.generated_skill_id,
        "rating": row.rating,
        "note": row.note or "",
        "correction_history_appended": appended,
        "created_at": row.created_at,
    }
