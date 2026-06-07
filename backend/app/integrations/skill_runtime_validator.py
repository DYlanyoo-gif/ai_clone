from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.llm_provider import LLMError, get_llm_provider

REQUIRED_BASE_FILES = ["SKILL.md", "README.md", "source_manifest.json"]
NUWA_FILES = ["persona.md", "thinking_framework.md", "decision_heuristics.md", "expression_dna.md"]
COLLEAGUE_FILES = ["persona.md", "work.md", "persona_skill.md", "work_skill.md"]
SENSITIVE_PATTERNS = [
    (".env", re.compile(r"(^|[\\/])\.env($|[\\/])", re.I)),
    ("database file", re.compile(r"\.(db|sqlite|sqlite3)$", re.I)),
    ("data directory", re.compile(r"(^|[\\/])data($|[\\/])", re.I)),
    ("uploads directory", re.compile(r"(^|[\\/])uploads($|[\\/])", re.I)),
    ("API key text", re.compile(r"api[_\s-]*key", re.I)),
    ("sk- token text", re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}", re.I)),
    ("bearer token text", re.compile(r"bearer\s+[A-Za-z0-9_\-\.]{10,}", re.I)),
]


def _read(path: Path, limit: int = 24000) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _check_skill_contract(skill_text: str) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []
    checks = {
        "name": [r"\bname\s*:", r"^# .+"],
        "description": [r"\bdescription\s*:"],
        "when_to_use": [r"when_to_use", r"触发", r"激活规则", r"使用方式"],
        "instructions": [r"instructions", r"执行协议", r"工作流", r"规则"],
        "inputs": [r"inputs", r"输入", r"读取 `"],
        "outputs": [r"outputs", r"输出", r"返回", r"生成"],
        "safety_boundary": [r"safety_boundary", r"安全边界", r"合规", r"不得", r"禁止"],
        "evidence_policy": [r"evidence_policy", r"证据", r"evidence_map", r"source_manifest"],
    }
    for name, patterns in checks.items():
        if any(re.search(p, skill_text, re.I | re.M) for p in patterns):
            passed.append(f"SKILL.md contains {name}")
        else:
            errors.append(f"SKILL.md 缺少 {name} / 类似说明")
    return errors, warnings, passed


def validate_skill_package(skill_path: str) -> dict[str, Any]:
    path = Path(skill_path)
    errors: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []

    if not path.exists() or not path.is_dir():
        return {
            "validation_score": 0,
            "runtime_ready": False,
            "level": "L4-compatible-generated",
            "passed_checks": [],
            "warnings": [],
            "errors": [f"Skill 目录不存在: {skill_path}"],
            "runtime_simulated": False,
            "actual_runtime_invoked": False,
        }
    passed.append("Skill directory exists")

    for filename in REQUIRED_BASE_FILES:
        if (path / filename).exists():
            passed.append(f"{filename} exists")
        else:
            errors.append(f"缺少 {filename}")

    skill_text = ""
    if (path / "SKILL.md").exists():
        skill_text = _read(path / "SKILL.md")
        e, w, p = _check_skill_contract(skill_text)
        errors.extend(e)
        warnings.extend(w)
        passed.extend(p)

    if (path / "source_manifest.json").exists():
        try:
            json.loads(_read(path / "source_manifest.json", 120000))
            passed.append("source_manifest.json is valid JSON")
        except json.JSONDecodeError as exc:
            errors.append(f"source_manifest.json 不是合法 JSON: {exc}")

    if (path / "evidence_map.md").exists():
        passed.append("evidence_map.md exists")
    else:
        warnings.append("缺少 evidence_map.md；Colleague 包可使用 work.md 中证据摘要，但建议保留 evidence_map.md")

    file_names = {p.name for p in path.iterdir() if p.is_file()}
    if "thinking_framework.md" in file_names or "decision_heuristics.md" in file_names:
        missing = [f for f in NUWA_FILES if f not in file_names]
        if missing:
            errors.append(f"Nuwa 包缺少: {', '.join(missing)}")
        else:
            passed.append("Nuwa required files exist")
    if "work.md" in file_names or "work_skill.md" in file_names:
        missing = [f for f in COLLEAGUE_FILES if f not in file_names]
        if missing:
            errors.append(f"Colleague 包缺少: {', '.join(missing)}")
        else:
            passed.append("Colleague Persona + Work files exist")

    for item in path.rglob("*"):
        rel = str(item.relative_to(path))
        for label, pattern in SENSITIVE_PATTERNS[:4]:
            if pattern.search(rel):
                errors.append(f"禁止打包敏感文件/目录: {rel} ({label})")
        if item.is_file() and item.stat().st_size <= 2_000_000:
            text = _read(item, 2_000_000)
            for label, pattern in SENSITIVE_PATTERNS[4:]:
                if pattern.search(text):
                    errors.append(f"文件疑似包含敏感文本: {rel} ({label})")

    total_checks = len(passed) + len(errors) + max(0, len(warnings) // 2)
    score = 0 if total_checks == 0 else round((len(passed) / total_checks) * 100)
    score = max(0, min(100, score))
    runtime_ready = not errors and score >= 80
    level = "L5-structure-validated" if runtime_ready else "L4-compatible-generated"
    return {
        "validation_score": score,
        "runtime_ready": runtime_ready,
        "level": level,
        "passed_checks": passed,
        "warnings": warnings,
        "errors": errors,
        "runtime_simulated": False,
        "actual_runtime_invoked": False,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


async def dry_run_skill_execution(skill_path: str, test_prompt: str) -> dict[str, Any]:
    path = Path(skill_path)
    used_files: list[str] = []
    warnings: list[str] = []
    parts: list[str] = []
    for filename in [
        "SKILL.md", "persona.md", "thinking_framework.md", "decision_heuristics.md",
        "expression_dna.md", "evidence_map.md", "work.md", "work_skill.md", "persona_skill.md",
    ]:
        file_path = path / filename
        if file_path.exists():
            used_files.append(filename)
            parts.append(f"\n\n## {filename}\n{_read(file_path, 9000)}")

    if not parts:
        return {
            "simulated_output": "",
            "used_files": [],
            "warnings": ["Skill 包没有可读取的 dry-run 文件。"],
            "runtime_simulated": False,
            "actual_runtime_invoked": False,
            "error": "no readable skill files",
        }

    runtime_prompt = (
        "你是一个 Agent Skill runtime dry-run 验证器。请根据以下 Skill 文件内容模拟一次运行，"
        "重点说明如何遵守 evidence_policy、安全边界，以及资料不足时如何回答。"
        "\n\n用户测试问题："
        f"{test_prompt}\n"
        "\nSkill 文件内容："
        + "".join(parts)
    )
    try:
        llm = get_llm_provider()
        output = await llm.generate_analysis(
            system_prompt="你只做本地 dry-run 模拟，不声称已经在 Codex/Claude/Hermes 外部 runtime 中执行。",
            user_prompt=runtime_prompt,
            temperature=0.3,
            max_tokens=1800,
        )
    except (LLMError, Exception) as exc:
        return {
            "simulated_output": "LLM provider unavailable，dry-run 未生成模型输出。",
            "used_files": used_files,
            "warnings": [f"LLM provider unavailable: {exc}"],
            "runtime_simulated": False,
            "actual_runtime_invoked": False,
            "error": str(exc),
        }

    return {
        "simulated_output": output,
        "used_files": used_files,
        "warnings": warnings,
        "runtime_simulated": True,
        "actual_runtime_invoked": False,
        "error": None,
    }
