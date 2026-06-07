from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.skill_foundry_common import (
    EXTERNAL_ROOT,
    GENERATED_ROOT,
    compact_markdown,
    evidence_summary,
    latest_profile_material,
    record_generated_skill,
    repo_status,
    safe_slug,
    source_manifest,
    write_files,
)

REPO_DIR = "colleague-skill"
REPO_URL = "https://github.com/titanwings/colleague-skill"


def detect() -> dict[str, Any]:
    return repo_status("colleague", REPO_DIR, REPO_URL)


def load_spec() -> dict[str, Any]:
    root = EXTERNAL_ROOT / REPO_DIR
    status = detect()
    read_files = [
        root / "README.md",
        root / "SKILL.md",
        root / "INSTALL.md",
        root / "prompts" / "work_builder.md",
        root / "prompts" / "persona_builder.md",
    ]
    if not status["installed"]:
        return {
            "name": "colleague",
            "source_repo": REPO_URL,
            "source_path": str(root),
            "project_name": "dot-skill / colleague-skill",
            "description": "仓库尚未导入，无法读取契约。",
            "skill_purpose": [],
            "input_requirements": [],
            "workflow": [],
            "output_contract": [],
            "runtime_hosts": [],
            "limitations": [status["detail"]],
            "raw_files_read": [],
        }

    return {
        "name": "colleague",
        "source_repo": REPO_URL,
        "source_path": str(root),
        "project_name": "dot-skill / colleague-skill",
        "description": "把同事、关系人物、公众人物等资料蒸馏成 Persona + Work 双层 Agent Skill。",
        "skill_purpose": [
            "从资料和描述生成可复用角色 Skill。",
            "Persona 负责态度、语气、表达和边界。",
            "Work Skill 负责工作范围、流程、标准和输出偏好。",
        ],
        "input_requirements": [
            "人物基本信息、关系或角色 family。",
            "聊天记录、文档、邮件、设计稿、评价、用户描述等资料。",
            "必要时可通过 Feishu / DingTalk / Slack 等工具采集，但 AI Clone 当前不调用这些采集器。",
        ],
        "workflow": [
            "Intake: 确认 family、slug、资料来源和目标。",
            "Analyze: Work 与 Persona 两条线抽取。",
            "Generate: 写入 SKILL.md、work.md、persona.md、meta.json。",
            "Evolve: 可追加资料、版本回滚和纠错。",
        ],
        "output_contract": [
            "SKILL.md",
            "persona.md",
            "work.md",
            "work_skill.md",
            "persona_skill.md",
            "meta.json",
            "manifest.json",
            "source_manifest.json",
            "README.md",
        ],
        "runtime_hosts": ["Claude Code", "Hermes", "OpenClaw", "Codex", "AgentSkills-compatible hosts"],
        "limitations": [
            "采集器依赖外部平台权限，AI Clone 当前不自动调用。",
            "生成角色不能冒充真人或代表本人真实意愿。",
            "资料越少，Persona / Work 推断越应保守。",
            "AI Clone 当前只生成兼容包，不安装到宿主 skill 目录。",
        ],
        "raw_files_read": [str(p) for p in read_files if p.exists()],
    }


def generate_profile_skill(db: Session, profile_id: int) -> dict[str, Any]:
    status = detect()
    spec = load_spec()
    material = latest_profile_material(db, profile_id)
    profile = material["profile"]
    latest = material["latest"]
    slug = safe_slug(profile.name, profile.id)
    out_dir = GENERATED_ROOT / slug / "colleague"

    repo_imported = bool(status["installed"])
    spec_parsed = repo_imported
    if not latest:
        row = record_generated_skill(
            db, profile_id, "colleague", REPO_URL, str(EXTERNAL_ROOT / REPO_DIR), str(out_dir),
            [], repo_imported, spec_parsed, False, False, "该人物尚未生成画像，无法蒸馏 Skill。",
        )
        return {"generated": False, "skill": row, "error": row.error, "detail": row.error}

    quality = material["quality"]
    sufficiency = material["sufficiency"]
    family = "colleague" if profile.relationship_type == "colleague" else "relationship"
    if profile.relationship_type in {"public_figure", "author", "celebrity"}:
        family = "celebrity"

    manifest = source_manifest(material)
    manifest["external_spec"] = {
        "repo": REPO_URL,
        "adapter": "colleague_skill_adapter",
        "family": family,
        "original_cli_invoked": False,
        "reason": "AI Clone 直接根据 evidence profile 写入兼容包，不调用 dot-skill 的采集、writer 或宿主安装流程。",
    }

    meta = {
        "name": slug,
        "display_name": profile.name,
        "character": family,
        "profile_id": profile.id,
        "classification": {"language": "zh-CN", "source": "AI Clone"},
        "source_system": "AI Clone / Echo Profile",
        "stats": {
            "document_count": len(material["docs"]),
            "chunk_count": material["chunk_count"],
            "total_chars": material["total_chars"],
            "evidence_coverage": quality.get("evidence_coverage", 0),
            "avg_confidence": quality.get("avg_confidence", 0),
            "sufficiency_label": sufficiency.get("label"),
        },
        "original_cli_invoked": False,
    }

    skill_md = f"""---
name: {family}-{slug}
description: |
  {profile.name} 的 dot-skill compatible package。由 AI Clone 基于资料画像生成，包含 Persona 与 Work 双层结构。
argument-hint: "[task]"
version: "1.0.0"
---

# {profile.name} · Dot-Skill Compatible Package

> 这是基于资料的 AI 模拟 Skill，不是本人意识，不代表本人真实意愿。

## 使用方式

- 需要语气、态度、边界和沟通方式时，读取 `persona.md`。
- 需要工作方式、判断标准、输出偏好时，读取 `work.md`。
- 需要证据来源时，读取 `manifest.json` 和 `source_manifest.json`。

## when_to_use

当任务需要基于 {profile.name} 的人物资料模拟工作方式、沟通风格、判断标准或关系互动模式时使用。

## instructions

1. 先确认任务是否适合该人物资料范围。
2. 资料相关问题必须优先依据 `persona.md` / `work.md` 中有证据的判断。
3. 若资料不足，明确说明推断边界。
4. 不得冒充真人、伪造授权、制造欺骗或输出违法用途内容。

## inputs

- 用户的新任务、问题或沟通场景。
- `persona.md`、`work.md`、`evidence_map.md`、`source_manifest.json`。

## outputs

- 以 Persona + Work 双层结构约束的分析、建议、模拟回复或工作判断。
- 必要时返回资料不足提示、证据边界和不可执行说明。

## safety_boundary

- 这是资料驱动的 AI 模拟，不是本人意识。
- 不代表本人真实意愿、授权、承诺、记忆或法律意见。
- 禁止用于冒充、诈骗、骚扰、伪造授权、遗嘱、法律/医疗/财务决定。

## evidence_policy

- 优先读取 `evidence_map.md` 和 `source_manifest.json`。
- 不得编造原始资料、chunk、文件名或人物经历。
- 资料不足时必须明确降低置信度。

## runtime_validation

结构验证通过只能说明本包具备 Agent Skill 基本结构；只有安装到 Codex / Claude Code / Hermes 等 runtime 并真实执行任务后，才能称为 actual runtime tested。
"""

    work_md = f"""# Work Skill

## Scope

- family: {family}
- relationship_type: {profile.relationship_type or "other"}
- 资料规模: {material["total_chars"]} 字 / {material["chunk_count"]} chunks
- 证据覆盖率: {quality.get("evidence_coverage", 0)}%

## Work Standards / Judgment Patterns

以下内容来自 AI Clone 14 模块画像和 evidence_map，适合作为任务判断、输出偏好与工作方式参考。

{compact_markdown(latest.portrait_report, 8000)}

## Evidence-Grounded Rules

{evidence_summary(latest.evidence_json, limit_claims=24)}
"""

    persona_md = f"""# Persona Skill

## Profile

- name: {profile.name}
- description: {profile.description or "（无）"}
- sufficiency: {sufficiency.get("label")}

## Persona / Expression / Boundaries

{compact_markdown(latest.style_card, 9000)}

## Safety Boundary

- 此 Skill 不代表本人真实意愿。
- 不得用于冒充、欺骗、骚扰、伪造授权或法律/医疗/财务决定。
- 资料不足时，以“有限资料下的推断”表达。
"""

    files = {
        "SKILL.md": skill_md,
        "persona.md": persona_md,
        "work.md": work_md,
        "evidence_map.md": f"# Evidence Map\n\n{evidence_summary(latest.evidence_json, limit_claims=28)}\n",
        "persona_skill.md": persona_md,
        "work_skill.md": work_md,
        "meta.json": json.dumps(meta, ensure_ascii=False, indent=2),
        "manifest.json": json.dumps(
            {
                "schema": "dot-skill-compatible",
                "source_repo": REPO_URL,
                "family": family,
                "files": ["SKILL.md", "persona.md", "work.md", "persona_skill.md", "work_skill.md", "meta.json"],
                "original_cli_invoked": False,
                "compatible_skill_generated": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "source_manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
        "README.md": f"""# {profile.name} Dot-Skill Compatible Package

此目录由 AI Clone 生成，用于兼容 dot-skill / colleague-skill 的 Persona + Work 双层结构。

- 外部仓库：{REPO_URL}
- family：{family}
- 原始 CLI 是否调用：否
- 未调用原因：本项目已有资料上传、MinerU 解析、DeepSeek 画像与 evidence_map，不执行 dot-skill 原始采集、writer 或宿主安装流程。
- 原始上传文件：未打包
- 敏感配置与凭据：未打包

已读取契约文件：
{chr(10).join(f"- {p}" for p in spec.get("raw_files_read", []))}
""",
    }
    generated_files = write_files(out_dir, files)
    row = record_generated_skill(
        db, profile_id, "colleague", REPO_URL, str(EXTERNAL_ROOT / REPO_DIR), str(out_dir),
        generated_files, repo_imported, spec_parsed, True, False, None,
    )
    return {"generated": True, "skill": row, "detail": "Dot-skill compatible Skill 包已生成。", "error": None}
