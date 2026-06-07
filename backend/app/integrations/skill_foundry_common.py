from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import AnalysisReport, Chunk, Document, GeneratedSkill, Profile
from app.services.profile_service import calculate_analysis_quality, get_data_sufficiency

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_ROOT = PROJECT_ROOT / "external"
GENERATED_ROOT = PROJECT_ROOT / "generated_skills"


def repo_status(name: str, repo_dir: str, repo_url: str) -> dict[str, Any]:
    path = EXTERNAL_ROOT / repo_dir
    installed = path.exists() and (path / "SKILL.md").exists()
    level = "L3" if installed else "L0"
    return {
        "name": name,
        "installed": installed,
        "available": installed,
        "source_repo": repo_url,
        "source_path": str(path),
        "error": None if installed else f"{repo_dir} not found under external/",
        "detail": "外部仓库已作为 submodule 导入，可读取 Skill 契约并生成兼容包。"
        if installed else "仅在文档中提及，尚未导入 external/。",
        "level": level,
        "level_label": "L3 仓库已导入" if installed else "L0 仅提及",
    }


def read_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def safe_slug(name: str, profile_id: int) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name.strip().lower(), flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-_")
    return f"{slug or 'profile'}-{profile_id}"


def latest_profile_material(db: Session, profile_id: int) -> dict[str, Any]:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError("人物档案不存在")

    latest = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    docs = db.query(Document).filter(Document.profile_id == profile_id).order_by(Document.uploaded_at.desc()).all()
    total_chars = (
        db.query(func.coalesce(func.sum(Chunk.char_count), 0))
        .filter(Chunk.profile_id == profile_id)
        .scalar() or 0
    )
    chunk_count = db.query(Chunk).filter(Chunk.profile_id == profile_id).count()
    quality = calculate_analysis_quality(db, profile_id) if chunk_count else {}
    sufficiency = get_data_sufficiency(total_chars, chunk_count)

    return {
        "profile": profile,
        "latest": latest,
        "docs": docs,
        "total_chars": total_chars,
        "chunk_count": chunk_count,
        "quality": quality,
        "sufficiency": sufficiency,
    }


def compact_markdown(text: str | None, limit: int = 9000) -> str:
    if not text:
        return "（暂无）"
    clean = text.strip()
    return clean[:limit] + ("\n\n（已截断，完整分析请查看 AI Clone 分析报告。）" if len(clean) > limit else "")


def evidence_summary(evidence_json: str | None, limit_claims: int = 18) -> str:
    if not evidence_json:
        return "当前档案尚未生成 evidence_map。"
    try:
        evidence = json.loads(evidence_json)
    except json.JSONDecodeError:
        return "evidence_map 解析失败。"

    lines: list[str] = []
    count = 0
    for module_key in sorted(evidence.keys(), key=lambda k: int(k) if str(k).isdigit() else 99):
        module = evidence.get(module_key)
        if not isinstance(module, dict):
            continue
        lines.append(f"## 模块 {module_key}: {module.get('module_name', '未命名')}")
        if not module.get("data_sufficient", True):
            lines.append("- 资料不足，需补充证据。")
            continue
        for claim in module.get("claims", []):
            if not isinstance(claim, dict) or count >= limit_claims:
                continue
            count += 1
            lines.append(f"- 判断: {claim.get('claim', '')} (confidence={claim.get('confidence_score', 0)})")
            for item in claim.get("evidence", [])[:2]:
                if isinstance(item, dict):
                    quote = str(item.get("quote", ""))[:260]
                    lines.append(
                        f"  - chunk_id={item.get('chunk_id', item.get('chunk_index', '?'))}, "
                        f"file={item.get('filename', '')}, retrieval={item.get('retrieval_method', 'keyword')}: {quote}"
                    )
    return "\n".join(lines) if lines else "当前 evidence_map 没有可展示证据。"


def source_manifest(material: dict[str, Any]) -> dict[str, Any]:
    docs = material["docs"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_system": "AI Clone / Echo Profile",
        "raw_files_included": False,
        "privacy_note": "此 manifest 仅记录文件元数据，不打包原始上传文件、数据库、.env 或敏感凭据。",
        "documents": [
            {
                "document_id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "parser": d.parser or "builtin",
                "char_count": d.char_count,
                "chunk_count": d.chunk_count,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            }
            for d in docs
        ],
    }


def write_files(base_dir: Path, files: dict[str, str]) -> list[str]:
    base_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel_path, content in files.items():
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written


def record_generated_skill(
    db: Session,
    profile_id: int,
    skill_type: str,
    source_repo: str,
    source_path: str,
    output_path: str,
    generated_files: list[str],
    repo_imported: bool,
    spec_parsed: bool,
    compatible_skill_generated: bool,
    original_cli_invoked: bool,
    error: str | None = None,
) -> GeneratedSkill:
    row = GeneratedSkill(
        profile_id=profile_id,
        skill_type=skill_type,
        source_repo=source_repo,
        source_path=source_path,
        output_path=output_path,
        generated_files_json=json.dumps(generated_files, ensure_ascii=False),
        status="created" if compatible_skill_generated else "failed",
        repo_imported=1 if repo_imported else 0,
        spec_parsed=1 if spec_parsed else 0,
        compatible_skill_generated=1 if compatible_skill_generated else 0,
        original_cli_invoked=1 if original_cli_invoked else 0,
        error=error,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def generated_skill_to_dict(row: GeneratedSkill) -> dict[str, Any]:
    try:
        generated_files = json.loads(row.generated_files_json or "[]")
    except json.JSONDecodeError:
        generated_files = []
    return {
        "id": row.id,
        "profile_id": row.profile_id,
        "skill_type": row.skill_type,
        "source_repo": row.source_repo,
        "source_path": row.source_path,
        "output_path": row.output_path,
        "generated_files": generated_files,
        "status": row.status,
        "repo_imported": bool(row.repo_imported),
        "spec_parsed": bool(row.spec_parsed),
        "compatible_skill_generated": bool(row.compatible_skill_generated),
        "original_cli_invoked": bool(row.original_cli_invoked),
        "validation_status": row.validation_status or "not_validated",
        "validation_score": row.validation_score or 0,
        "validation_passed_checks": json.loads(row.validation_passed_checks_json or "[]"),
        "validation_errors": json.loads(row.validation_errors_json or "[]"),
        "validation_warnings": json.loads(row.validation_warnings_json or "[]"),
        "runtime_simulated": bool(row.runtime_simulated),
        "actual_runtime_invoked": bool(row.actual_runtime_invoked),
        "runtime_test_output_path": row.runtime_test_output_path or "",
        "install_instructions_path": row.install_instructions_path or "",
        "last_validated_at": row.last_validated_at,
        "l5c_runtime_target": row.l5c_runtime_target or "",
        "l5c_passed": bool(row.l5c_passed),
        "l5c_score": row.l5c_score or 0,
        "l5c_result_id": row.l5c_result_id,
        "l5c_validated_at": row.l5c_validated_at,
        "error": row.error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
