from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.integrations import colleague_skill_adapter, nuwa_skill_adapter
from app.integrations.skill_runtime_testcases import generate_runtime_test_cases
from app.integrations.skill_runtime_validator import dry_run_skill_execution, validate_skill_package
from app.models.database import Chunk, GeneratedSkill, Profile
from app.services.profile_service import generate_analysis_report

logger = logging.getLogger(__name__)


DEFAULT_PIPELINE_OPTIONS: dict[str, bool] = {
    "run_analysis": True,
    "generate_nuwa_skill": True,
    "generate_colleague_skill": True,
    "validate_skills": True,
    "prepare_website_runtime": True,
    "run_dry_run": False,
    "generate_runtime_testcases": False,
}


def _step(status: str = "pending", detail: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "detail": detail}
    payload.update(extra)
    return payload


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload or [], ensure_ascii=False)


def _persist_validation(db: Session, row: GeneratedSkill, result: dict[str, Any]) -> None:
    row.validation_score = int(result.get("validation_score", 0) or 0)
    row.validation_status = result.get("level", "L4-compatible-generated")
    row.validation_passed_checks_json = _json_dumps(result.get("passed_checks", []))
    row.validation_errors_json = _json_dumps(result.get("errors", []))
    row.validation_warnings_json = _json_dumps(result.get("warnings", []))
    row.runtime_simulated = 1 if result.get("runtime_simulated") else int(row.runtime_simulated or 0)
    row.actual_runtime_invoked = 1 if result.get("actual_runtime_invoked") else int(row.actual_runtime_invoked or 0)
    row.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)


def _latest_skill(db: Session, profile_id: int, skill_type: str) -> GeneratedSkill | None:
    return (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.profile_id == profile_id, GeneratedSkill.skill_type == skill_type)
        .order_by(GeneratedSkill.created_at.desc())
        .first()
    )


async def _maybe_dry_run(db: Session, row: GeneratedSkill, warnings: list[str]) -> None:
    dry = await dry_run_skill_execution(
        row.output_path,
        "请说明你会如何使用 evidence_policy，并指出资料不足时应该如何回答。",
    )
    if dry.get("error"):
        warnings.append(f"{row.skill_type} dry-run 未完成：{dry.get('error')}")
    validation = validate_skill_package(row.output_path)
    validation["runtime_simulated"] = bool(dry.get("runtime_simulated"))
    validation["actual_runtime_invoked"] = False
    _persist_validation(db, row, validation)


async def run_profile_analysis_pipeline(
    db: Session,
    profile_id: int,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    opts = {**DEFAULT_PIPELINE_OPTIONS, **(options or {})}
    warnings: list[str] = []
    errors: list[str] = []
    next_actions: list[str] = []

    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return {
            "profile_id": profile_id,
            "pipeline_status": "failed",
            "analysis_ready": False,
            "evidence_ready": False,
            "skills_ready": False,
            "runtime_ready": False,
            "nuwa_skill_id": None,
            "colleague_skill_id": None,
            "analysis_status": _step("failed", "人物档案不存在"),
            "evidence_status": _step("failed", "人物档案不存在"),
            "nuwa_skill_status": _step("pending"),
            "colleague_skill_status": _step("pending"),
            "validation_status": _step("pending"),
            "website_runtime_ready": False,
            "warnings": warnings,
            "errors": ["人物档案不存在"],
            "next_actions": ["返回人物列表并选择有效档案"],
        }

    chunk_count = db.query(Chunk).filter(Chunk.profile_id == profile_id).count()
    if chunk_count == 0:
        logger.info("profile pipeline need_upload profile_id=%s chunk_count=0", profile_id)
        return {
            "profile_id": profile_id,
            "pipeline_status": "need_upload",
            "analysis_ready": False,
            "evidence_ready": False,
            "skills_ready": False,
            "runtime_ready": False,
            "nuwa_skill_id": None,
            "colleague_skill_id": None,
            "analysis_status": _step("pending", "等待资料上传"),
            "evidence_status": _step("pending", "等待资料上传"),
            "nuwa_skill_status": _step("pending", "等待画像完成"),
            "colleague_skill_status": _step("pending", "等待画像完成"),
            "validation_status": _step("pending", "等待 Skill 生成"),
            "website_runtime_ready": False,
            "warnings": warnings,
            "errors": [],
            "next_actions": ["请先上传 txt / md / PDF / Office / 图片资料"],
        }

    analysis_ready = False
    evidence_ready = False
    analysis_status = _step("pending")
    evidence_status = _step("pending")

    if opts["run_analysis"]:
        try:
            report = await generate_analysis_report(db=db, profile_id=profile_id)
            analysis_ready = bool(report.portrait_report and report.style_card)
            evidence_ready = bool(report.evidence_json)
            analysis_status = _step(
                "done" if analysis_ready else "warning",
                "证据画像已生成" if analysis_ready else "画像已生成，但内容不完整",
                analysis_id=report.id,
                model_used=report.model_used,
            )
            evidence_status = _step(
                "done" if evidence_ready else "warning",
                "证据链已生成" if evidence_ready else "画像完成，但 evidence_map 缺失或为空",
            )
            if not evidence_ready:
                warnings.append("本次画像未生成完整 evidence_map，建议重试或补充资料。")
        except Exception as exc:
            logger.exception("Profile analysis pipeline failed for profile=%s", profile_id)
            errors.append(f"画像分析失败：{exc}")
            return {
                "profile_id": profile_id,
                "pipeline_status": "failed",
                "analysis_ready": False,
                "evidence_ready": False,
                "skills_ready": False,
                "runtime_ready": False,
                "nuwa_skill_id": None,
                "colleague_skill_id": None,
                "analysis_status": _step("failed", f"画像分析失败：{exc}"),
                "evidence_status": _step("failed", "主画像失败，证据链未生成"),
                "nuwa_skill_status": _step("pending", "主画像失败，未生成"),
                "colleague_skill_status": _step("pending", "主画像失败，未生成"),
                "validation_status": _step("pending", "主画像失败，未验证"),
                "website_runtime_ready": False,
                "warnings": warnings,
                "errors": errors,
                "next_actions": ["检查 LLM provider 配置或稍后重试"],
            }

    nuwa_row: GeneratedSkill | None = _latest_skill(db, profile_id, "nuwa")
    colleague_row: GeneratedSkill | None = _latest_skill(db, profile_id, "colleague")
    nuwa_status = _step("pending")
    colleague_status = _step("pending")

    if opts["generate_nuwa_skill"]:
        try:
            result = nuwa_skill_adapter.generate_profile_skill(db, profile_id)
            nuwa_row = result.get("skill") or _latest_skill(db, profile_id, "nuwa")
            if result.get("generated") and nuwa_row:
                nuwa_status = _step("done", "Nuwa Skill 已生成", skill_id=nuwa_row.id)
            else:
                detail = result.get("detail") or result.get("error") or "Nuwa Skill 生成未完成"
                warnings.append(detail)
                nuwa_status = _step("warning", detail, skill_id=nuwa_row.id if nuwa_row else None)
        except Exception as exc:
            logger.exception("Nuwa skill generation failed for profile=%s", profile_id)
            warnings.append(f"Nuwa Skill 生成失败：{exc}")
            nuwa_status = _step("warning", f"Nuwa Skill 生成失败：{exc}")

    if opts["generate_colleague_skill"]:
        try:
            result = colleague_skill_adapter.generate_profile_skill(db, profile_id)
            colleague_row = result.get("skill") or _latest_skill(db, profile_id, "colleague")
            if result.get("generated") and colleague_row:
                colleague_status = _step("done", "Colleague Skill 已生成", skill_id=colleague_row.id)
            else:
                detail = result.get("detail") or result.get("error") or "Colleague Skill 生成未完成"
                warnings.append(detail)
                colleague_status = _step("warning", detail, skill_id=colleague_row.id if colleague_row else None)
        except Exception as exc:
            logger.exception("Colleague skill generation failed for profile=%s", profile_id)
            warnings.append(f"Colleague Skill 生成失败：{exc}")
            colleague_status = _step("warning", f"Colleague Skill 生成失败：{exc}")

    validation_status = _step("pending")
    validation_errors = 0
    validated_count = 0
    if opts["validate_skills"]:
        for row in [nuwa_row, colleague_row]:
            if not row:
                continue
            try:
                validation = validate_skill_package(row.output_path)
                _persist_validation(db, row, validation)
                validated_count += 1
                validation_errors += len(validation.get("errors", []))
                for item in validation.get("warnings", []):
                    warnings.append(f"{row.skill_type} 验证提示：{item}")
                for item in validation.get("errors", []):
                    warnings.append(f"{row.skill_type} 结构验证未完全通过：{item}")
                if opts["run_dry_run"]:
                    await _maybe_dry_run(db, row, warnings)
                if opts["generate_runtime_testcases"]:
                    try:
                        generate_runtime_test_cases(row.output_path, row.skill_type, "codex")
                    except Exception as exc:
                        warnings.append(f"{row.skill_type} runtime 测试用例生成失败：{exc}")
            except Exception as exc:
                logger.exception("Skill validation failed for profile=%s skill=%s", profile_id, row.id)
                warnings.append(f"{row.skill_type} Skill 验证失败：{exc}")
                validation_errors += 1

        if validated_count == 0:
            validation_status = _step("warning", "没有可验证的 Skill 包")
        elif validation_errors:
            validation_status = _step("warning", f"已验证 {validated_count} 个 Skill，存在 {validation_errors} 个结构问题")
        else:
            validation_status = _step("done", f"已验证 {validated_count} 个 Skill")

    skills_ready = bool(nuwa_row and colleague_row)
    runtime_ready = bool(opts["prepare_website_runtime"] and skills_ready)

    if runtime_ready:
        next_actions.append("可进入模拟实验台，运行 Nuwa / Colleague / 双引擎对比。")
    elif not skills_ready:
        next_actions.append("画像已生成，但 Skill 未完全准备；可展开高级技术详情查看原因。")
    if not evidence_ready:
        next_actions.append("建议补充资料或重新分析，以提高证据覆盖率。")

    pipeline_status = "completed"
    if errors:
        pipeline_status = "failed"
    elif warnings or not skills_ready or not evidence_ready:
        pipeline_status = "partial"

    return {
        "profile_id": profile_id,
        "pipeline_status": pipeline_status,
        "analysis_ready": analysis_ready,
        "evidence_ready": evidence_ready,
        "skills_ready": skills_ready,
        "runtime_ready": runtime_ready,
        "nuwa_skill_id": nuwa_row.id if nuwa_row else None,
        "colleague_skill_id": colleague_row.id if colleague_row else None,
        "analysis_status": analysis_status,
        "evidence_status": evidence_status,
        "nuwa_skill_status": nuwa_status,
        "colleague_skill_status": colleague_status,
        "validation_status": validation_status,
        "website_runtime_ready": runtime_ready,
        "warnings": warnings,
        "errors": errors,
        "next_actions": next_actions,
    }
