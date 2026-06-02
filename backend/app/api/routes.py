from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import Profile, Document, Chunk, AnalysisReport, ChatMessage
from app.models.session import get_db
from app.schemas.models import (
    ProfileCreate, ProfileResponse, ProfileDetail,
    DocumentResponse, AnalysisResponse,
    ChatRequest, ChatResponse, ChatMessageResponse,
    MessageResponse, ErrorResponse, MineruStatusResponse,
    Mem0StatusResponse, MemoryRebuildResponse, MemorySearchRequest,
)
from app.services.document_processor import parse_file_content
from app.services.profile_service import (
    process_document_upload, generate_analysis_report, chat_with_profile,
    export_skill_card, get_data_sufficiency,
)
from app.services.llm_provider import get_config_status
from app.integrations.easy_dataset_adapter import export_chunks_jsonl
from app.integrations.llamafactory_adapter import export_sft_dataset, export_sft_jsonl
from app.integrations.mineru_adapter import detect_mineru, parse_with_mineru, MineruStatus
from app.integrations.mem0_adapter import detect_mem0, rebuild_memories_sync, search_memory_sync
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
