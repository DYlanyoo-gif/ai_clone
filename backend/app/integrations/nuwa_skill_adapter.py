from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.skill_foundry_common import (
    EXTERNAL_ROOT,
    GENERATED_ROOT,
    compact_markdown,
    evidence_summary,
    latest_profile_material,
    read_text,
    record_generated_skill,
    repo_status,
    safe_slug,
    source_manifest,
    write_files,
)

REPO_DIR = "nuwa-skill"
REPO_URL = "https://github.com/alchaincyf/nuwa-skill"


def detect() -> dict[str, Any]:
    return repo_status("nuwa", REPO_DIR, REPO_URL)


def load_spec() -> dict[str, Any]:
    root = EXTERNAL_ROOT / REPO_DIR
    status = detect()
    read_files = [
        root / "README.md",
        root / "SKILL.md",
        root / "references" / "skill-template.md",
        root / "references" / "extraction-framework.md",
    ]
    if not status["installed"]:
        return {
            "name": "nuwa",
            "source_repo": REPO_URL,
            "source_path": str(root),
            "project_name": "nuwa-skill",
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
        "name": "nuwa",
        "source_repo": REPO_URL,
        "source_path": str(root),
        "project_name": "女娲.skill / Nuwa Skill",
        "description": "从公开或本地资料提炼人物的心智模型、决策启发式、表达 DNA 与诚实边界，生成可运行的人物 perspective skill。",
        "skill_purpose": [
            "蒸馏一个人的 HOW they think，而不是复读 WHAT they said。",
            "构建认知操作系统：心智模型、判断规则、表达 DNA、反模式与边界。",
            "将人物视角转为 Agent Skills 兼容的 SKILL.md。",
        ],
        "input_requirements": [
            "人物名称、用途和聚焦方向。",
            "一手资料优先：长文、访谈、作品、决策记录、社交表达。",
            "明确标注资料来源、可信度和信息不足维度。",
        ],
        "workflow": [
            "Phase 0 需求澄清与目录创建。",
            "Phase 1 多源资料采集和六维研究。",
            "Phase 2 三重验证提炼心智模型。",
            "Phase 3 按模板构建 SKILL.md。",
            "Phase 4 质量验证与诚实边界标注。",
        ],
        "output_contract": [
            "SKILL.md",
            "persona.md",
            "thinking_framework.md",
            "decision_heuristics.md",
            "expression_dna.md",
            "evidence_map.md",
            "source_manifest.json",
            "README.md",
        ],
        "runtime_hosts": ["Claude Code", "Codex", "Cursor", "OpenClaw", "Hermes", "AgentSkills-compatible hosts"],
        "limitations": [
            "不能复制本人意识或真实意愿。",
            "公开表达不等于真实想法。",
            "资料不足时必须降低置信度并保留边界。",
            "AI Clone 当前只生成兼容包，不执行 Nuwa 原始多 agent 调研流程。",
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
    out_dir = GENERATED_ROOT / slug / "nuwa"

    repo_imported = bool(status["installed"])
    spec_parsed = repo_imported
    if not latest:
        row = record_generated_skill(
            db, profile_id, "nuwa", REPO_URL, str(EXTERNAL_ROOT / REPO_DIR), str(out_dir),
            [], repo_imported, spec_parsed, False, False, "该人物尚未生成画像，无法蒸馏 Skill。",
        )
        return {"generated": False, "skill": row, "error": row.error, "detail": row.error}

    quality = material["quality"]
    sufficiency = material["sufficiency"]
    manifest = source_manifest(material)
    manifest["external_spec"] = {
        "repo": REPO_URL,
        "adapter": "nuwa_skill_adapter",
        "original_cli_invoked": False,
        "reason": "AI Clone 使用既有 evidence profile 生成兼容 Skill 包，不调用 Nuwa 原始多 agent 采集流程。",
    }

    skill_md = f"""---
name: {slug}-nuwa-perspective
description: |
  {profile.name} 的人物思维框架 Skill。由 AI Clone 根据已上传资料、证据画像和 Nuwa Skill 契约生成。
  用途：以证据约束的方式分析此人的认知框架、表达 DNA、决策启发式和诚实边界。
---

# {profile.name} · Nuwa-Compatible Perspective Skill

> 这是 AI Clone 基于用户上传资料生成的模拟分析 Skill，不是本人意识，不代表本人真实意愿。

## 激活规则

- 当用户要求“用 {profile.name} 的视角分析”“切换到 {profile.name} 思维框架”“查看此人的决策方式”时使用。
- 回答必须基于本包中的 evidence_map、thinking_framework、decision_heuristics 和 expression_dna。
- 资料不足时明确说“根据当前资料只能有限推断”，不得编造经历、授权、承诺或本人意愿。
- 不用于冒充真人、诈骗、骚扰、法律/医疗/财务决定或伪造授权。

## when_to_use

当任务需要用 {profile.name} 的资料画像分析新问题、解释思维框架、模拟表达风格或检查证据边界时使用。

## instructions

1. 先读取 `persona.md` 获取人物摘要和边界。
2. 再读取 `thinking_framework.md` 选择最相关的心智模型。
3. 需要判断或建议时，读取 `decision_heuristics.md`。
4. 需要模拟表达时，读取 `expression_dna.md`，保持克制，不做夸张模仿。
5. 输出前查阅 `evidence_map.md`，优先引用有 chunk_id / filename / confidence 的证据。

## inputs

- 用户提出的新问题或分析任务。
- 本包内的 persona、thinking framework、decision heuristics、expression DNA 与 evidence map。

## outputs

- 基于资料证据的分析、建议或模拟表达。
- 必要时返回资料不足提示、证据来源摘要和不确定性边界。

## safety_boundary

- 不能声称自己是本人。
- 不能代表本人真实意愿、授权、承诺或记忆。
- 禁止用于冒充、诈骗、骚扰、伪造授权、遗嘱、法律/医疗/财务决定。

## evidence_policy

- 优先使用 `evidence_map.md` 和 `source_manifest.json`。
- 证据不足时必须说明“当前资料不足，无法可靠判断”。
- 不得编造 chunk、文件名、引用或原始资料。

## 档案摘要

- 关系类型：{profile.relationship_type or "other"}
- 资料充分度：{sufficiency.get("label")} / {material["total_chars"]} 字 / {material["chunk_count"]} chunks
- 证据覆盖率：{quality.get("evidence_coverage", 0)}%
- 平均置信度：{quality.get("avg_confidence", 0)}

## runtime_validation

结构验证通过只能说明本包具备 Agent Skill 基本结构；只有安装到 Codex / Claude Code / Hermes 等 runtime 并真实执行任务后，才能称为 actual runtime tested。
"""

    files = {
        "SKILL.md": skill_md,
        "persona.md": f"# Persona Snapshot\n\n{compact_markdown(latest.portrait_report, 10000)}\n",
        "thinking_framework.md": f"# Thinking Framework\n\n基于 Nuwa 契约，本文件承载可运行的心智模型提炼。\n\n{compact_markdown(latest.portrait_report, 8000)}\n",
        "decision_heuristics.md": f"# Decision Heuristics\n\n从 14 模块画像和证据链中提炼的判断规则。使用时必须回看 evidence_map。\n\n{evidence_summary(latest.evidence_json)}\n",
        "expression_dna.md": f"# Expression DNA\n\n{compact_markdown(latest.style_card, 8000)}\n",
        "evidence_map.md": f"# Evidence Map\n\n{evidence_summary(latest.evidence_json, limit_claims=28)}\n",
        "source_manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
        "README.md": f"""# {profile.name} Nuwa-Compatible Skill Package

此目录由 AI Clone 生成，用于兼容 Nuwa Skill 的人物思维框架结构。

- 外部仓库：{REPO_URL}
- 原始 CLI 是否调用：否
- 未调用原因：本项目已有 MinerU / DeepSeek / evidence_map 画像流程，本包只做兼容输出，不执行 Nuwa 原始调研和宿主安装流程。
- 原始上传文件：未打包
- 敏感配置与凭据：未打包

已读取契约文件：
{chr(10).join(f"- {p}" for p in spec.get("raw_files_read", []))}
""",
    }
    generated_files = write_files(out_dir, files)
    row = record_generated_skill(
        db, profile_id, "nuwa", REPO_URL, str(EXTERNAL_ROOT / REPO_DIR), str(out_dir),
        generated_files, repo_imported, spec_parsed, True, False, None,
    )
    return {"generated": True, "skill": row, "detail": "Nuwa-compatible Skill 包已生成。", "error": None}
