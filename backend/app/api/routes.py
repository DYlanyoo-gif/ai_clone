from __future__ import annotations

import logging
import os
import json
import zipfile
from io import BytesIO
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import Profile, Document, Chunk, AnalysisReport, ChatMessage, GeneratedSkill, RuntimeValidationResult
from app.models.session import get_db
from app.schemas.models import (
    ProfileCreate, ProfileResponse, ProfileDetail,
    DocumentResponse, AnalysisResponse,
    ProfilePipelineOptions, ProfilePipelineResponse,
    ChatRequest, ChatResponse, ChatMessageResponse,
    MessageResponse, ErrorResponse, MineruStatusResponse,
    Mem0StatusResponse, MemoryRebuildResponse, MemorySearchRequest,
    VectorStatusResponse, VectorRebuildResponse, VectorSearchResponse,
    SkillIntegrationStatusResponse, SkillSpecResponse, GeneratedSkillResponse,
    SkillGenerateResponse, SkillValidationResponse, SkillDryRunRequest,
    RuntimeTestCaseRequest, RuntimeTestCasesResponse, RuntimeResultSubmitRequest,
    RuntimeResultResponse, RuntimeEvaluationResponse,
    SkillWebsiteRunRequest, SkillRuntimeRunResponse, SkillCompareRunRequest,
    SkillCompareRunResponse, SkillRuntimeFeedbackRequest, SkillRuntimeFeedbackResponse,
)
from app.services.document_processor import parse_file_content
from app.services.profile_service import (
    process_document_upload, generate_analysis_report, chat_with_profile,
    export_skill_card, get_data_sufficiency, calculate_analysis_quality,
    export_analysis_report,
)
from app.services.profile_pipeline_service import run_profile_analysis_pipeline
from app.services.llm_provider import get_config_status
from app.integrations.easy_dataset_adapter import export_chunks_jsonl
from app.integrations.llamafactory_adapter import export_sft_dataset, export_sft_jsonl
from app.integrations.mineru_adapter import detect_mineru, parse_with_mineru, MineruStatus
from app.integrations.mem0_adapter import detect_mem0, rebuild_memories_sync, search_memory_sync
from app.integrations.vector_adapter import detect_vector, collection_info, index_chunks, delete_document_vectors
from app.integrations import nuwa_skill_adapter, colleague_skill_adapter
from app.integrations.skill_foundry_common import generated_skill_to_dict
from app.integrations.skill_runtime_validator import validate_skill_package, dry_run_skill_execution
from app.integrations.skill_installer import prepare_runtime_install_bundle
from app.integrations.skill_runtime_testcases import (
    generate_runtime_test_cases, load_runtime_test_cases, evaluate_runtime_result,
)
from app.services.skill_runtime_service import (
    run_skill_in_website, list_skill_runtime_runs, get_skill_runtime_run,
    compare_skill_runs, submit_skill_runtime_feedback,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv"}
MINERU_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".webp"}

settings = get_settings()


# ── Health ──

@router.get("/health")
async def api_health():
    return {"status": "ok", "service": "ai-clone-backend"}


# ── Data Sufficiency ──

@router.get("/profiles/{profile_id}/sufficiency")
async def get_profile_sufficiency(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.profile_id == profile_id).scalar() or 0
    total_chars = (
        db.query(func.coalesce(func.sum(Chunk.char_count), 0))
        .filter(Chunk.profile_id == profile_id)
        .scalar() or 0
    )

    return get_data_sufficiency(total_chars, chunk_count)


# ── Config Status (safe, no API key exposed) ──

@router.get("/config/status")
async def config_status():
    return get_config_status()


# ── MinerU Integration Status ──

@router.get("/integrations/mineru/status", response_model=MineruStatusResponse)
async def mineru_status():
    """Check whether MinerU is installed, which CLI is available, current config, and whether it's enabled."""
    status = detect_mineru()
    s = settings
    return MineruStatusResponse(
        installed=status.installed,
        command=status.command,
        version_or_help=status.version_or_help,
        error=status.error,
        enabled=status.enabled,
        backend=s.mineru_backend,
        method=s.mineru_method,
        lang=s.mineru_lang,
        formula=s.mineru_formula,
        table=s.mineru_table,
        image_analysis=s.mineru_image_analysis,
        timeout_seconds=s.mineru_timeout_seconds,
    )


# ── mem0 Integration Status ──

@router.get("/integrations/mem0/status", response_model=Mem0StatusResponse)
async def mem0_status():
    """Check whether mem0 is installed, enabled, and API-compatible."""
    status = detect_mem0()
    detail = ""
    if not status.installed:
        detail = "mem0 未安装。安装: pip install mem0ai"
    elif not status.available:
        detail = "mem0 已安装但客户端初始化失败，可能是 API 版本不兼容。"
    elif not status.enabled:
        detail = "mem0 已安装但未启用。在 .env 中设置 MEM0_ENABLED=true 并重启后端。"
    else:
        detail = "mem0 已安装、已启用、API 可用。"
    return Mem0StatusResponse(
        installed=status.installed,
        enabled=status.enabled,
        available=status.available,
        provider=status.provider,
        error=status.error,
        detail=detail,
    )


# ── Vector Retrieval Integration Status ──

@router.get("/integrations/vector/status", response_model=VectorStatusResponse)
async def vector_status(profile_id: int | None = None):
    """Check Qdrant/FastEmbed optional vector retrieval status.

    profile_id is optional and only used to report the local collection state.
    """
    status = detect_vector()
    info = collection_info(profile_id) if profile_id else {}
    return VectorStatusResponse(
        installed=status.installed,
        enabled=status.enabled,
        available=status.available,
        provider=status.provider,
        embedding_model=status.embedding_model,
        error=status.error,
        detail=status.detail,
        collection=info.get("collection"),
        points_count=info.get("points_count", 0),
        indexed=info.get("indexed", False),
    )


# ── Skill Foundry Integration Status ──

@router.get("/integrations/nuwa/status", response_model=SkillIntegrationStatusResponse)
async def nuwa_status():
    return nuwa_skill_adapter.detect()


@router.get("/integrations/nuwa/spec", response_model=SkillSpecResponse)
async def nuwa_spec():
    return nuwa_skill_adapter.load_spec()


@router.get("/integrations/colleague/status", response_model=SkillIntegrationStatusResponse)
async def colleague_status():
    return colleague_skill_adapter.detect()


@router.get("/integrations/colleague/spec", response_model=SkillSpecResponse)
async def colleague_spec():
    return colleague_skill_adapter.load_spec()


# ── Profile CRUD ──

@router.post("/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(data: ProfileCreate, db: Session = Depends(get_db)):
    profile = Profile(
        name=data.name,
        description=data.description,
        relationship_type=data.relationship_type,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    logger.info(f"Created profile: {profile.id} - {profile.name}")
    return _to_profile_response(profile, 0, 0, False)


@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(db: Session = Depends(get_db)):
    profiles = db.query(Profile).order_by(Profile.created_at.desc()).all()
    result = []
    for p in profiles:
        doc_count, chunk_count, has_analysis = _profile_counts(db, p.id)
        result.append(_to_profile_response(p, doc_count, chunk_count, has_analysis))
    return result


@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
async def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    doc_count, chunk_count, has_analysis = _profile_counts(db, profile_id)

    # Compute total chars from chunks
    total_chars = (
        db.query(func.coalesce(func.sum(Chunk.char_count), 0))
        .filter(Chunk.profile_id == profile_id)
        .scalar() or 0
    )

    latest_analysis = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )

    analysis_quality = calculate_analysis_quality(db, profile_id) if total_chars > 0 else None

    return ProfileDetail(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        relationship_type=profile.relationship_type,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        document_count=doc_count,
        chunk_count=chunk_count,
        total_chars=total_chars,
        has_analysis=has_analysis,
        latest_portrait=latest_analysis.portrait_report if latest_analysis else None,
        latest_style_card=latest_analysis.style_card if latest_analysis else None,
        evidence_json=latest_analysis.evidence_json if latest_analysis else None,
        analysis_quality=analysis_quality,
    )


# ── Documents ──

@router.post("/profiles/{profile_id}/documents", response_model=MessageResponse)
async def upload_document(
    profile_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    # Validate extension
    filename = file.filename or "unknown.txt"
    ext = ("." + filename.split(".")[-1].lower()) if "." in filename else ""
    all_allowed = ALLOWED_EXTENSIONS | MINERU_EXTENSIONS
    if ext not in all_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式。支持的格式: "
                   f"{', '.join(sorted(ALLOWED_EXTENSIONS | MINERU_EXTENSIONS))}",
        )

    # Read content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    # ── Plain text files (existing flow, unchanged) ──
    if ext in ALLOWED_EXTENSIONS:
        try:
            text, content_type = parse_file_content(content, filename)
            if not text.strip():
                raise HTTPException(status_code=400, detail="解析后文件内容为空")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"文件解析失败: {e}")

        try:
            result = await process_document_upload(
                db=db,
                profile_id=profile_id,
                filename=filename,
                text=text,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"Document processing failed: {e}")
            raise HTTPException(status_code=500, detail=f"文档处理失败: {e}")

        return MessageResponse(
            message="文件上传成功",
            detail=f"已处理 {result['chunk_count']} 个文本片段，共 {result['char_count']} 字符",
        )

    # ── Complex documents (PDF, DOCX, PPTX, XLSX, images) via MinerU ──
    # Check MinerU is available
    mineru = detect_mineru()
    if not mineru.installed:
        raise HTTPException(
            status_code=400,
            detail="当前未安装 MinerU，无法解析 PDF/DOCX/PPTX/XLSX/图片文件。"
                   "请先运行: powershell -ExecutionPolicy Bypass -File scripts/install_mineru_windows.ps1，"
                   "或上传 txt/md/json/csv 文件。",
        )

    if not mineru.enabled:
        raise HTTPException(
            status_code=400,
            detail="MinerU 已安装但未启用。请在 .env 中设置 MINERU_ENABLED=true",
        )

    # Save original file
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"{profile_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
    orig_path = os.path.join(upload_dir, safe_name)
    with open(orig_path, "wb") as f:
        f.write(content)
    logger.info(f"Saved original file: {orig_path}")

    # Parse with MinerU
    try:
        parsed = parse_with_mineru(orig_path)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"文件保存失败，无法找到: {orig_path}")
    except RuntimeError as e:
        logger.exception(f"MinerU parse error for {filename}")
        raise HTTPException(status_code=422, detail=f"MinerU 解析失败: {e}")
    except Exception as e:
        logger.exception(f"Unexpected MinerU error for {filename}")
        raise HTTPException(status_code=500, detail=f"文档解析异常: {e}")

    parsed_text = parsed.text
    if not parsed_text.strip():
        raise HTTPException(
            status_code=422,
            detail="解析结果为空。可能文档是扫描件、图片质量低或 MinerU 未正确识别内容。"
                   "建议使用文本格式（txt/md）上传，或尝试更清晰的文档。",
        )

    if len(parsed_text.strip()) < 50:
        logger.warning(
            f"Short parse result ({len(parsed_text)} chars) for {filename}. "
            f"Warnings: {parsed.warnings}"
        )

    # Process parsed text through existing pipeline
    try:
        result = await process_document_upload(
            db=db,
            profile_id=profile_id,
            filename=filename,
            text=parsed_text,
            parser=parsed.parser,
            parsed_text_path=parsed.markdown_path,
            original_file_path=orig_path,
            parse_status="success",
            parse_error=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Document processing failed after MinerU: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {e}")

    warning_note = ""
    if parsed.warnings:
        warning_note = f"（注意: {'; '.join(parsed.warnings)}）"
    if len(parsed_text.strip()) < 50:
        warning_note += " 解析结果过短，可能文档是扫描件、图片质量低或 MinerU 未正确识别。"

    return MessageResponse(
        message="文件上传并解析成功",
        detail=f"使用 {parsed.parser} 解析，已处理 {result['chunk_count']} 个文本片段，"
               f"共 {result['char_count']} 字符。{warning_note}",
    )


@router.get("/profiles/{profile_id}/documents", response_model=list[DocumentResponse])
async def list_documents(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")
    docs = db.query(Document).filter(Document.profile_id == profile_id).order_by(Document.uploaded_at.desc()).all()
    return docs


# ── Analysis ──

@router.post("/profiles/{profile_id}/analyze", response_model=AnalysisResponse)
async def analyze_profile(profile_id: int, db: Session = Depends(get_db)):
    chunks = db.query(Chunk).filter(Chunk.profile_id == profile_id).count()
    if chunks == 0:
        raise HTTPException(status_code=400, detail="该人物没有任何资料，请先上传资料。")

    try:
        report = await generate_analysis_report(
            db=db,
            profile_id=profile_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    return report


@router.post("/profiles/{profile_id}/pipeline/analyze", response_model=ProfilePipelineResponse)
async def analyze_profile_pipeline(
    profile_id: int,
    req: ProfilePipelineOptions | None = None,
    db: Session = Depends(get_db),
):
    logger.info("pipeline analyze requested profile_id=%s step=start", profile_id)
    result = await run_profile_analysis_pipeline(
        db=db,
        profile_id=profile_id,
        options=req.model_dump() if req else None,
    )
    logger.info(
        "pipeline analyze completed profile_id=%s status=%s errors=%s warnings=%s",
        profile_id,
        result.get("pipeline_status"),
        len(result.get("errors", [])),
        len(result.get("warnings", [])),
    )
    if result.get("pipeline_status") == "failed" and "人物档案不存在" in result.get("errors", []):
        raise HTTPException(status_code=404, detail="人物档案不存在")
    return result


@router.get("/profiles/{profile_id}/analysis", response_model=list[AnalysisResponse])
async def list_analyses(profile_id: int, db: Session = Depends(get_db)):
    analyses = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .all()
    )
    return analyses


# ── Chat ──

@router.post("/profiles/{profile_id}/chat", response_model=ChatResponse)
async def chat(profile_id: int, req: ChatRequest, db: Session = Depends(get_db)):
    try:
        result = await chat_with_profile(
            db=db,
            profile_id=profile_id,
            user_message=req.message,
            mode=req.mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"对话失败: {e}")

    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    return ChatResponse(
        reply=result["reply"],
        profile_name=profile.name if profile else "",
        retrieved_count=result["retrieved_count"],
        model_used=result["model_used"],
        retrieval_method=result.get("retrieval_method", "keyword"),
        retrieved_chunks=result.get("retrieved_chunks", []),
    )


@router.get("/profiles/{profile_id}/chat", response_model=list[ChatMessageResponse])
async def list_chat_messages(profile_id: int, db: Session = Depends(get_db)):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.profile_id == profile_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(100)
        .all()
    )
    return messages


# ── Vector Retrieval ──

@router.post("/profiles/{profile_id}/vector/rebuild", response_model=VectorRebuildResponse)
async def rebuild_profile_vectors(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    status = detect_vector()
    if not status.installed:
        return VectorRebuildResponse(
            indexed=0,
            error=status.error or "vector dependencies not installed",
            detail="向量检索依赖未安装。请运行: pip install qdrant-client fastembed",
        )
    if not status.enabled:
        return VectorRebuildResponse(
            indexed=0,
            error="VECTOR_ENABLED=false",
            detail="向量检索未启用。请在 .env 中设置 VECTOR_ENABLED=true 并重启后端。",
        )
    if not status.available:
        return VectorRebuildResponse(
            indexed=0,
            error=status.error or "vector unavailable",
            detail="向量检索初始化失败，当前仍使用关键词检索 fallback。",
        )

    rows = (
        db.query(Chunk, Document.filename, Document.parser)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )
    chunks = [
        {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "profile_id": profile_id,
            "filename": filename,
            "chunk_index": chunk.chunk_index,
            "parser": doc_parser or chunk.parser or "builtin",
            "char_count": chunk.char_count,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else "",
            "content": chunk.content,
        }
        for chunk, filename, doc_parser in rows
    ]

    try:
        result = index_chunks(profile_id, chunks)
    except Exception as e:
        logger.exception("Vector rebuild failed for profile %s", profile_id)
        return VectorRebuildResponse(
            indexed=0,
            error=str(e),
            detail="向量索引重建失败，当前仍可使用关键词检索 fallback。",
        )

    return VectorRebuildResponse(
        indexed=int(result.get("indexed", 0)),
        error=result.get("error"),
        detail=f"已重建 {int(result.get('indexed', 0))} 个文本片段的向量索引。",
    )


@router.get("/profiles/{profile_id}/vector/search", response_model=VectorSearchResponse)
async def search_profile_vectors(profile_id: int, query: str = "", db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")
    if not query.strip():
        return VectorSearchResponse(query="", retrieval_method="keyword", results=[], total=0)

    from app.services.profile_service import search_relevant_chunks

    results, method = search_relevant_chunks(db, profile_id, query, top_k=settings.vector_top_k)
    return VectorSearchResponse(
        query=query,
        retrieval_method=method,
        results=results,
        total=len(results),
    )


# ── Skill Foundry ──

@router.get("/profiles/{profile_id}/skills", response_model=list[GeneratedSkillResponse])
async def list_profile_generated_skills(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")
    rows = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.profile_id == profile_id)
        .order_by(GeneratedSkill.created_at.desc())
        .all()
    )
    return [generated_skill_to_dict(row) for row in rows]


@router.get("/profiles/{profile_id}/skills/{skill_id}", response_model=GeneratedSkillResponse)
async def get_profile_generated_skill(profile_id: int, skill_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.id == skill_id, GeneratedSkill.profile_id == profile_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="生成的 Skill 不存在")
    return generated_skill_to_dict(row)


@router.post("/profiles/{profile_id}/skills/nuwa/generate", response_model=SkillGenerateResponse)
async def generate_nuwa_skill(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")
    result = nuwa_skill_adapter.generate_profile_skill(db, profile_id)
    row = result.get("skill")
    return SkillGenerateResponse(
        generated=bool(result.get("generated")),
        skill=generated_skill_to_dict(row) if row else None,
        detail=result.get("detail", ""),
        error=result.get("error"),
    )


@router.post("/profiles/{profile_id}/skills/colleague/generate", response_model=SkillGenerateResponse)
async def generate_colleague_skill(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")
    result = colleague_skill_adapter.generate_profile_skill(db, profile_id)
    row = result.get("skill")
    return SkillGenerateResponse(
        generated=bool(result.get("generated")),
        skill=generated_skill_to_dict(row) if row else None,
        detail=result.get("detail", ""),
        error=result.get("error"),
    )


@router.post("/profiles/{profile_id}/skills/nuwa/validate", response_model=SkillValidationResponse)
async def validate_latest_nuwa_skill(profile_id: int, db: Session = Depends(get_db)):
    row = _latest_generated_skill_by_type(db, profile_id, "nuwa")
    result = validate_skill_package(row.output_path)
    _persist_validation(db, row, result)
    return _validation_response(result, row)


@router.post("/profiles/{profile_id}/skills/colleague/validate", response_model=SkillValidationResponse)
async def validate_latest_colleague_skill(profile_id: int, db: Session = Depends(get_db)):
    row = _latest_generated_skill_by_type(db, profile_id, "colleague")
    result = validate_skill_package(row.output_path)
    _persist_validation(db, row, result)
    return _validation_response(result, row)


def _get_generated_skill_row(db: Session, profile_id: int, skill_id: int) -> GeneratedSkill:
    row = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.id == skill_id, GeneratedSkill.profile_id == profile_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="生成的 Skill 不存在")
    return row


def _latest_generated_skill_by_type(db: Session, profile_id: int, skill_type: str) -> GeneratedSkill:
    row = (
        db.query(GeneratedSkill)
        .filter(GeneratedSkill.profile_id == profile_id, GeneratedSkill.skill_type == skill_type)
        .order_by(GeneratedSkill.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"尚未生成 {skill_type} Skill 包")
    return row


def _persist_validation(db: Session, row: GeneratedSkill, result: dict) -> None:
    if not row.l5c_passed:
        row.validation_status = result.get("level", "L4-compatible-generated")
    row.validation_score = int(result.get("validation_score", 0) or 0)
    row.validation_passed_checks_json = json.dumps(result.get("passed_checks", []), ensure_ascii=False)
    row.validation_errors_json = json.dumps(result.get("errors", []), ensure_ascii=False)
    row.validation_warnings_json = json.dumps(result.get("warnings", []), ensure_ascii=False)
    row.runtime_simulated = 1 if result.get("runtime_simulated") else int(row.runtime_simulated or 0)
    row.actual_runtime_invoked = 1 if result.get("actual_runtime_invoked") else int(row.actual_runtime_invoked or 0)
    row.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)


def _validation_response(result: dict, row: GeneratedSkill | None = None) -> SkillValidationResponse:
    return SkillValidationResponse(
        validation_score=int(result.get("validation_score", row.validation_score if row else 0) or 0),
        runtime_ready=bool(result.get("runtime_ready", False)),
        level=result.get("level", row.validation_status if row else "L4-compatible-generated"),
        passed_checks=result.get("passed_checks", []),
        warnings=result.get("warnings", []),
        errors=result.get("errors", []),
        runtime_simulated=bool(result.get("runtime_simulated", row.runtime_simulated if row else False)),
        actual_runtime_invoked=bool(result.get("actual_runtime_invoked", row.actual_runtime_invoked if row else False)),
        install_instructions_path=(row.install_instructions_path if row else "") or result.get("install_instructions_path", ""),
        simulated_output=result.get("simulated_output"),
        used_files=result.get("used_files", []),
        error=result.get("error"),
    )


def _runtime_result_to_response(row: RuntimeValidationResult) -> RuntimeResultResponse:
    return RuntimeResultResponse(
        id=row.id,
        generated_skill_id=row.generated_skill_id,
        profile_id=row.profile_id,
        skill_type=row.skill_type,
        runtime_target=row.runtime_target,
        tester_note=row.tester_note or "",
        test_output_text=row.test_output_text or "",
        score=row.score or 0,
        passed=bool(row.passed),
        failed_cases=json.loads(row.failed_cases_json or "[]"),
        warnings=json.loads(row.warnings_json or "[]"),
        evidence_of_runtime=row.evidence_of_runtime or "",
        created_at=row.created_at,
    )


@router.post("/profiles/{profile_id}/skills/compare-run", response_model=SkillCompareRunResponse)
async def compare_generated_skills_in_website(
    profile_id: int,
    req: SkillCompareRunRequest,
    db: Session = Depends(get_db),
):
    try:
        result = await compare_skill_runs(
            db,
            profile_id=profile_id,
            nuwa_skill_id=req.nuwa_skill_id,
            colleague_skill_id=req.colleague_skill_id,
            user_prompt=req.user_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SkillCompareRunResponse(**result)


@router.post("/profiles/{profile_id}/skills/{skill_id}/run", response_model=SkillRuntimeRunResponse)
async def run_generated_skill_in_website(
    profile_id: int,
    skill_id: int,
    req: SkillWebsiteRunRequest,
    db: Session = Depends(get_db),
):
    try:
        result = await run_skill_in_website(
            db,
            profile_id=profile_id,
            skill_id=skill_id,
            user_prompt=req.user_prompt,
            runtime_mode=req.runtime_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SkillRuntimeRunResponse(**result)


@router.get("/profiles/{profile_id}/skills/{skill_id}/runs", response_model=list[SkillRuntimeRunResponse])
async def list_generated_skill_website_runs(
    profile_id: int,
    skill_id: int,
    db: Session = Depends(get_db),
):
    _get_generated_skill_row(db, profile_id, skill_id)
    return [SkillRuntimeRunResponse(**item) for item in list_skill_runtime_runs(db, profile_id, skill_id)]


@router.get("/profiles/{profile_id}/skills/{skill_id}/runs/{run_id}", response_model=SkillRuntimeRunResponse)
async def get_generated_skill_website_run(
    profile_id: int,
    skill_id: int,
    run_id: int,
    db: Session = Depends(get_db),
):
    _get_generated_skill_row(db, profile_id, skill_id)
    try:
        result = get_skill_runtime_run(db, profile_id, skill_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SkillRuntimeRunResponse(**result)


@router.post("/profiles/{profile_id}/skills/{skill_id}/runs/{run_id}/feedback", response_model=SkillRuntimeFeedbackResponse)
async def submit_generated_skill_website_run_feedback(
    profile_id: int,
    skill_id: int,
    run_id: int,
    req: SkillRuntimeFeedbackRequest,
    db: Session = Depends(get_db),
):
    _get_generated_skill_row(db, profile_id, skill_id)
    try:
        result = submit_skill_runtime_feedback(
            db,
            profile_id=profile_id,
            skill_id=skill_id,
            run_id=run_id,
            rating=req.rating,
            note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SkillRuntimeFeedbackResponse(**result)


@router.post("/profiles/{profile_id}/skills/{skill_id}/validate", response_model=SkillValidationResponse)
async def validate_generated_skill(profile_id: int, skill_id: int, db: Session = Depends(get_db)):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    result = validate_skill_package(row.output_path)
    _persist_validation(db, row, result)
    return _validation_response(result, row)


@router.get("/profiles/{profile_id}/skills/{skill_id}/validation", response_model=SkillValidationResponse)
async def get_generated_skill_validation(profile_id: int, skill_id: int, db: Session = Depends(get_db)):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    return _validation_response(
        {
            "validation_score": row.validation_score or 0,
            "runtime_ready": (row.validation_status or "").startswith("L5"),
            "level": row.validation_status or "not_validated",
            "passed_checks": json.loads(row.validation_passed_checks_json or "[]"),
            "warnings": json.loads(row.validation_warnings_json or "[]"),
            "errors": json.loads(row.validation_errors_json or "[]"),
            "runtime_simulated": bool(row.runtime_simulated),
            "actual_runtime_invoked": bool(row.actual_runtime_invoked),
        },
        row,
    )


@router.post("/profiles/{profile_id}/skills/{skill_id}/dry-run", response_model=SkillValidationResponse)
async def dry_run_generated_skill(
    profile_id: int,
    skill_id: int,
    req: SkillDryRunRequest | None = None,
    db: Session = Depends(get_db),
):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    validation = validate_skill_package(row.output_path)
    dry = await dry_run_skill_execution(
        row.output_path,
        (req.test_prompt if req else "请说明你会如何使用 evidence_policy，并指出资料不足时应该如何回答。"),
    )
    output_path = os.path.join(row.output_path, "runtime_dry_run_output.md")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Runtime Dry Run Output\n\n")
            f.write(f"- runtime_simulated: {bool(dry.get('runtime_simulated'))}\n")
            f.write("- actual_runtime_invoked: false\n")
            f.write(f"- used_files: {', '.join(dry.get('used_files', []))}\n\n")
            f.write(dry.get("simulated_output") or "")
        row.runtime_test_output_path = output_path
    except Exception as e:
        dry.setdefault("warnings", []).append(f"dry-run output 写入失败: {e}")

    level = "L5-dry-run-simulated" if dry.get("runtime_simulated") else validation.get("level", "L4-compatible-generated")
    result = {
        **validation,
        "level": level,
        "runtime_simulated": bool(dry.get("runtime_simulated")),
        "actual_runtime_invoked": False,
        "simulated_output": dry.get("simulated_output"),
        "used_files": dry.get("used_files", []),
        "warnings": list(validation.get("warnings", [])) + list(dry.get("warnings", [])),
        "errors": list(validation.get("errors", [])),
        "error": dry.get("error"),
    }
    _persist_validation(db, row, result)
    return _validation_response(result, row)


@router.get("/profiles/{profile_id}/skills/{skill_id}/install-instructions", response_model=SkillValidationResponse)
async def generated_skill_install_instructions(
    profile_id: int,
    skill_id: int,
    target: str = "generic_agent_skill",
    db: Session = Depends(get_db),
):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    result = prepare_runtime_install_bundle(row.output_path, target)
    row.install_instructions_path = result.get("instructions_path", "")
    db.commit()
    db.refresh(row)
    return _validation_response(
        {
            "validation_score": row.validation_score or 0,
            "level": row.validation_status or "L4-compatible-generated",
            "warnings": result.get("warnings", []),
            "errors": [],
            "install_instructions_path": row.install_instructions_path,
            "runtime_simulated": bool(row.runtime_simulated),
            "actual_runtime_invoked": bool(row.actual_runtime_invoked),
        },
        row,
    )


@router.post("/profiles/{profile_id}/skills/{skill_id}/runtime-testcases", response_model=RuntimeTestCasesResponse)
async def create_generated_skill_runtime_testcases(
    profile_id: int,
    skill_id: int,
    req: RuntimeTestCaseRequest | None = None,
    db: Session = Depends(get_db),
):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    result = generate_runtime_test_cases(
        row.output_path,
        row.skill_type,
        req.runtime_target if req else "codex",
    )
    return RuntimeTestCasesResponse(**result)


@router.get("/profiles/{profile_id}/skills/{skill_id}/runtime-testcases", response_model=RuntimeTestCasesResponse)
async def get_generated_skill_runtime_testcases(
    profile_id: int,
    skill_id: int,
    runtime_target: str = "codex",
    db: Session = Depends(get_db),
):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    payload = load_runtime_test_cases(row.output_path)
    cases = payload.get("test_cases", [])
    md_path = os.path.join(row.output_path, "runtime_test_cases.md")
    json_path = os.path.join(row.output_path, "runtime_test_cases.json")
    if not cases:
        result = generate_runtime_test_cases(row.output_path, row.skill_type, runtime_target)
        return RuntimeTestCasesResponse(**result)
    return RuntimeTestCasesResponse(
        runtime_target=payload.get("runtime_target", runtime_target),
        markdown_path=md_path if os.path.exists(md_path) else "",
        json_path=json_path if os.path.exists(json_path) else "",
        test_cases=cases,
        warnings=[],
    )


@router.post("/profiles/{profile_id}/skills/{skill_id}/runtime-results", response_model=RuntimeResultResponse)
async def submit_generated_skill_runtime_result(
    profile_id: int,
    skill_id: int,
    req: RuntimeResultSubmitRequest,
    db: Session = Depends(get_db),
):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    result = RuntimeValidationResult(
        generated_skill_id=row.id,
        profile_id=profile_id,
        skill_type=row.skill_type,
        runtime_target=req.runtime_target,
        tester_note=req.tester_note,
        test_output_text=req.test_output_text,
        score=0,
        passed=0,
        failed_cases_json="[]",
        warnings_json=json.dumps(["尚未评估；请点击评估运行结果。"], ensure_ascii=False),
        evidence_of_runtime=req.evidence_of_runtime,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return _runtime_result_to_response(result)


@router.get("/profiles/{profile_id}/skills/{skill_id}/runtime-results", response_model=list[RuntimeResultResponse])
async def list_generated_skill_runtime_results(profile_id: int, skill_id: int, db: Session = Depends(get_db)):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    results = (
        db.query(RuntimeValidationResult)
        .filter(RuntimeValidationResult.profile_id == profile_id, RuntimeValidationResult.generated_skill_id == row.id)
        .order_by(RuntimeValidationResult.created_at.desc())
        .all()
    )
    return [_runtime_result_to_response(item) for item in results]


@router.post("/profiles/{profile_id}/skills/{skill_id}/runtime-results/evaluate", response_model=RuntimeEvaluationResponse)
async def evaluate_generated_skill_runtime_result(
    profile_id: int,
    skill_id: int,
    req: RuntimeResultSubmitRequest,
    db: Session = Depends(get_db),
):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    if not os.path.exists(os.path.join(row.output_path, "runtime_test_cases.json")):
        generate_runtime_test_cases(row.output_path, row.skill_type, req.runtime_target)
    evaluation = await evaluate_runtime_result(
        row.output_path,
        req.runtime_target,
        req.test_output_text,
        req.tester_note,
    )
    result = RuntimeValidationResult(
        generated_skill_id=row.id,
        profile_id=profile_id,
        skill_type=row.skill_type,
        runtime_target=req.runtime_target,
        tester_note=req.tester_note,
        test_output_text=req.test_output_text,
        score=int(evaluation.get("score", 0) or 0),
        passed=1 if evaluation.get("can_mark_l5c") else 0,
        failed_cases_json=json.dumps(evaluation.get("failed_cases", []), ensure_ascii=False),
        warnings_json=json.dumps(evaluation.get("warnings", []), ensure_ascii=False),
        evidence_of_runtime=req.evidence_of_runtime,
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    if evaluation.get("can_mark_l5c"):
        row.l5c_runtime_target = req.runtime_target
        row.l5c_passed = 1
        row.l5c_score = int(evaluation.get("score", 0) or 0)
        row.l5c_result_id = result.id
        row.l5c_validated_at = datetime.now(timezone.utc)
        row.validation_status = "L5c-actual-runtime-tested"
        row.actual_runtime_invoked = 1
        db.commit()
        db.refresh(row)

    return RuntimeEvaluationResponse(
        result_id=result.id,
        score=int(evaluation.get("score", 0) or 0),
        passed=bool(evaluation.get("passed", False)),
        failed_cases=evaluation.get("failed_cases", []),
        warnings=evaluation.get("warnings", []),
        recommended_fix=evaluation.get("recommended_fix", ""),
        can_mark_l5c=bool(evaluation.get("can_mark_l5c", False)),
        judgeable_cases=int(evaluation.get("judgeable_cases", 0) or 0),
        safety_boundary_passed=bool(evaluation.get("safety_boundary_passed", False)),
        evidence_policy_passed=bool(evaluation.get("evidence_policy_passed", False)),
    )


@router.get("/profiles/{profile_id}/skills/{skill_id}/download")
async def download_generated_skill(profile_id: int, skill_id: int, db: Session = Depends(get_db)):
    row = _get_generated_skill_row(db, profile_id, skill_id)
    if not row.output_path or not os.path.isdir(row.output_path):
        raise HTTPException(status_code=404, detail="生成目录不存在，请重新生成。")

    base_dir = os.path.abspath(row.output_path)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_dir):
            for filename in files:
                path = os.path.abspath(os.path.join(root, filename))
                if not path.startswith(base_dir):
                    continue
                arcname = os.path.relpath(path, base_dir)
                zf.write(path, arcname)
    buffer.seek(0)
    filename = f"{row.skill_type}_skill_profile_{profile_id}_{skill_id}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Memory (mem0) ──

@router.post("/profiles/{profile_id}/memory/rebuild", response_model=MemoryRebuildResponse)
async def rebuild_memory(profile_id: int, db: Session = Depends(get_db)):
    """Rebuild mem0 memories from existing chat history and analysis.
    Requires MEM0_ENABLED=true and mem0 installed."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    mem0_status = detect_mem0()
    if not mem0_status.enabled:
        return MemoryRebuildResponse(stored=0, error="mem0 未启用。请在 .env 中设置 MEM0_ENABLED=true 并重启后端。")
    if not mem0_status.installed:
        return MemoryRebuildResponse(stored=0, error="mem0 未安装。请运行: pip install mem0ai")
    if not mem0_status.available:
        return MemoryRebuildResponse(stored=0, error=f"mem0 已安装但不可用: {mem0_status.error}")

    style_card = ""
    latest_analysis = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.profile_id == profile_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    if latest_analysis:
        style_card = latest_analysis.style_card or ""

    result = rebuild_memories_sync(profile_id, profile.name, style_card)
    return MemoryRebuildResponse(stored=result["stored"], error=result["error"])


@router.get("/profiles/{profile_id}/memory/search")
async def search_memory(profile_id: int, q: str = "", limit: int = 5):
    """Search mem0 memories for a profile.
    Returns clear messages when mem0 is not available."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    mem0_status = detect_mem0()
    if not mem0_status.enabled:
        return {"results": [], "query": q, "total": 0, "status": "mem0 未启用。请在 .env 中设置 MEM0_ENABLED=true。"}
    if not mem0_status.installed:
        return {"results": [], "query": q, "total": 0, "status": "mem0 未安装。请运行: pip install mem0ai"}
    if not mem0_status.available:
        return {"results": [], "query": q, "total": 0, "status": f"mem0 不可用: {mem0_status.error}"}

    if not q.strip():
        return {"results": [], "query": "", "total": 0, "status": "ok"}

    results = search_memory_sync(f"profile_{profile_id}", q, limit)
    return {"results": results, "query": q, "total": len(results), "status": "ok"}


# ── Document Management ──

@router.delete("/profiles/{profile_id}/documents/{document_id}")
async def delete_document(profile_id: int, document_id: int, db: Session = Depends(get_db)):
    """Delete a document and its chunks. Original uploaded file is preserved on disk
    (MinerU output files are kept for debugging; only database records are removed)."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.profile_id == profile_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # Delete chunks first (ON DELETE CASCADE handles this, but explicit is safer)
    db.query(Chunk).filter(Chunk.document_id == document_id).delete()
    filename = doc.filename
    db.delete(doc)
    db.commit()

    try:
        delete_document_vectors(profile_id, document_id)
    except Exception as e:
        logger.warning("Vector cleanup skipped for profile=%s document=%s: %s", profile_id, document_id, e)

    logger.info(f"Deleted document {document_id} ({filename}) for profile {profile_id}")
    return MessageResponse(
        message="文档已删除",
        detail=f"已删除文档 \"{filename}\" 及其所有文本片段。原始上传文件保留在磁盘上。",
    )


@router.post("/profiles/{profile_id}/rebuild-chunks")
async def rebuild_chunks(profile_id: int, db: Session = Depends(get_db)):
    """Rebuild chunks for all documents in a profile. Useful after MinerU config changes
    or if chunking parameters need to be re-applied."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    from app.services.document_processor import parse_file_content

    docs = (
        db.query(Document)
        .filter(Document.profile_id == profile_id)
        .all()
    )

    rebuilt = 0
    errors = []

    for doc in docs:
        try:
            # Delete existing chunks
            db.query(Chunk).filter(Chunk.document_id == doc.id).delete()

            # Re-parse the stored parsed text path if available, otherwise use existing
            if doc.parsed_text_path and os.path.isfile(doc.parsed_text_path):
                with open(doc.parsed_text_path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            elif doc.original_file_path and os.path.isfile(doc.original_file_path):
                with open(doc.original_file_path, "rb") as f:
                    raw = f.read()
                text, _ = parse_file_content(raw, doc.filename)
            else:
                errors.append(f"{doc.filename}: 原始文件或解析文本路径不可用")
                continue

            if not text.strip():
                errors.append(f"{doc.filename}: 解析文本为空")
                continue

            # Re-chunk using the same logic as process_document_upload
            from app.services.profile_service import process_document_upload
            await process_document_upload(
                db=db,
                profile_id=profile_id,
                filename=doc.filename,
                text=text,
                parser=doc.parser,
                parsed_text_path=doc.parsed_text_path,
                original_file_path=doc.original_file_path,
                parse_status="success",
            )
            rebuilt += 1
        except Exception as e:
            errors.append(f"{doc.filename}: {e}")

    msg = f"已重建 {rebuilt} 个文档的文本片段"
    if errors:
        msg += f"，{len(errors)} 个失败: {'; '.join(errors[:5])}"
    return MessageResponse(message="重建完成", detail=msg)


@router.get("/profiles/{profile_id}/documents/{document_id}/preview")
async def preview_document(profile_id: int, document_id: int, db: Session = Depends(get_db)):
    """Return the first 3000 chars of parsed text for a document preview."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.profile_id == profile_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    text = ""
    source = ""

    # Try parsed text path first (MinerU output)
    if doc.parsed_text_path and os.path.isfile(doc.parsed_text_path):
        with open(doc.parsed_text_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(3000)
        source = "parsed_text"
    elif doc.original_file_path and os.path.isfile(doc.original_file_path):
        ext = os.path.splitext(doc.filename)[1].lower()
        if ext in (".txt", ".md", ".markdown", ".json", ".csv"):
            with open(doc.original_file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(3000)
            source = "original"
        else:
            text = f"[二进制文件，无法直接预览。解析器: {doc.parser or '未知'}]"
            source = "binary"
    else:
        text = "[文件路径不可用]"
        source = "missing"

    return {
        "document_id": document_id,
        "filename": doc.filename,
        "parser": doc.parser,
        "parse_status": doc.parse_status,
        "char_count": doc.char_count,
        "preview_text": text,
        "source": source,
    }


# ── Analysis Quality ──

@router.get("/profiles/{profile_id}/quality")
async def get_analysis_quality(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    quality = calculate_analysis_quality(db, profile_id)
    chunks = (
        db.query(Chunk, Document.filename, Document.parser, Document.file_type)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.profile_id == profile_id)
        .all()
    )

    # Build enriched chunk list
    chunk_list = []
    for chunk, filename, doc_parser, file_type in chunks[:20]:
        chunk_list.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "filename": filename,
            "chunk_index": chunk.chunk_index,
            "content_preview": chunk.content[:200],
            "char_count": chunk.char_count,
            "parser": doc_parser or chunk.parser or "builtin",
        })

    return {
        "profile_id": profile_id,
        "profile_name": profile.name,
        "quality": quality,
        "sample_chunks": chunk_list,
    }


# ── Export ──

@router.get("/profiles/{profile_id}/export/skill-card")
async def export_profile_skill_card(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    try:
        markdown = export_skill_card(db, profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "profile_id": profile_id,
        "profile_name": profile.name,
        "format": "markdown",
        "filename": f"SKILL_{profile.name}.md",
        "content": markdown,
    }


@router.get("/profiles/{profile_id}/export/analysis-report")
async def export_analysis_report_endpoint(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    try:
        markdown = export_analysis_report(db, profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "profile_id": profile_id,
        "profile_name": profile.name,
        "format": "markdown",
        "filename": f"analysis_report_{profile.name}.md",
        "content": markdown,
    }


@router.get("/profiles/{profile_id}/export/dataset")
async def export_profile_dataset(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    chunks = db.query(Chunk).filter(Chunk.profile_id == profile_id).count()
    if chunks == 0:
        raise HTTPException(status_code=400, detail="该人物没有资料，请先上传资料。")

    data = export_chunks_jsonl(db, profile_id, include_chat=True)
    return {
        "profile_id": profile_id,
        "profile_name": profile.name,
        "format": "jsonl",
        "filename": f"dataset_{profile.name}.jsonl",
        "total_records": len(data),
        "records": data,
    }


@router.get("/profiles/{profile_id}/export/sft")
async def export_profile_sft(profile_id: int, db: Session = Depends(get_db)):
    """Export chat messages in LLaMA Factory SFT format (messages JSONL)."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人物档案不存在")

    chat_count = db.query(ChatMessage).filter(ChatMessage.profile_id == profile_id).count()
    if chat_count < 2:
        raise HTTPException(
            status_code=400,
            detail="该人物对话数据不足（需要至少一轮对话）。请先进行几轮聊天后再导出 SFT 数据集。",
        )

    data = export_sft_jsonl(db, profile_id)
    return {
        "profile_id": profile_id,
        "profile_name": profile.name,
        "format": "llamafactory_sft_jsonl",
        "filename": f"sft_{profile.name}.jsonl",
        "total_records": len(data.split("\n")) if data else 0,
        "content": data,
    }


# ── Helpers ──

def _profile_counts(db: Session, profile_id: int) -> tuple[int, int, bool]:
    doc_count = db.query(func.count(Document.id)).filter(Document.profile_id == profile_id).scalar() or 0
    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.profile_id == profile_id).scalar() or 0
    has_analysis = db.query(AnalysisReport).filter(AnalysisReport.profile_id == profile_id).count() > 0
    return doc_count, chunk_count, has_analysis


def _to_profile_response(profile: Profile, doc_count: int, chunk_count: int, has_analysis: bool) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        relationship_type=profile.relationship_type,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        document_count=doc_count,
        chunk_count=chunk_count,
        has_analysis=has_analysis,
    )
