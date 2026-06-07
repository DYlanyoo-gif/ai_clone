from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Any | None = None
_embedding_model: Any | None = None
_vector_size: int | None = None


@dataclass
class VectorStatus:
    installed: bool
    enabled: bool
    available: bool
    provider: str
    embedding_model: str
    error: str | None = None
    detail: str = ""


def _import_qdrant():
    from qdrant_client import QdrantClient
    from qdrant_client import models

    return QdrantClient, models


def _import_fastembed():
    from fastembed import TextEmbedding

    return TextEmbedding


def _collection_name(profile_id: int) -> str:
    s = get_settings()
    safe_prefix = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in s.vector_collection_prefix)
    return f"{safe_prefix}_{profile_id}"


def detect_vector() -> VectorStatus:
    """Detect optional vector retrieval dependencies and current availability.

    This never raises. When VECTOR_ENABLED=false, it only checks imports and
    avoids initializing the embedding model.
    """
    s = get_settings()
    qdrant_ok = False
    fastembed_ok = False
    errors: list[str] = []

    try:
        _import_qdrant()
        qdrant_ok = True
    except Exception as e:
        errors.append(f"qdrant-client 未安装或不可用: {e}")

    try:
        _import_fastembed()
        fastembed_ok = True
    except Exception as e:
        errors.append(f"fastembed 未安装或不可用: {e}")

    installed = qdrant_ok and fastembed_ok
    if not installed:
        return VectorStatus(
            installed=False,
            enabled=s.vector_enabled,
            available=False,
            provider=s.vector_provider,
            embedding_model=s.vector_embedding_model,
            error="; ".join(errors),
            detail="向量检索依赖未安装。安装: pip install qdrant-client fastembed",
        )

    if not s.vector_enabled:
        return VectorStatus(
            installed=True,
            enabled=False,
            available=False,
            provider=s.vector_provider,
            embedding_model=s.vector_embedding_model,
            detail="向量检索依赖已安装，但 VECTOR_ENABLED=false；当前使用关键词检索 fallback。",
        )

    try:
        _get_client()
        _get_embedding_model()
        return VectorStatus(
            installed=True,
            enabled=True,
            available=True,
            provider=s.vector_provider,
            embedding_model=s.vector_embedding_model,
            detail="Qdrant local + FastEmbed 已启用，可用于语义证据检索。",
        )
    except Exception as e:
        return VectorStatus(
            installed=True,
            enabled=True,
            available=False,
            provider=s.vector_provider,
            embedding_model=s.vector_embedding_model,
            error=str(e),
            detail="向量检索已启用但初始化失败，系统会自动回退关键词检索。",
        )


def is_vector_available() -> bool:
    status = detect_vector()
    return status.enabled and status.installed and status.available


def _get_client():
    global _client
    if _client is not None:
        return _client

    s = get_settings()
    if s.vector_provider != "qdrant":
        raise RuntimeError(f"不支持的向量检索 provider: {s.vector_provider}")

    QdrantClient, _ = _import_qdrant()
    qdrant_path = Path(s.vector_qdrant_path).resolve()
    qdrant_path.mkdir(parents=True, exist_ok=True)
    _client = QdrantClient(path=str(qdrant_path))
    return _client


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    s = get_settings()
    if s.vector_embedding_provider != "fastembed":
        raise RuntimeError(f"不支持的 embedding provider: {s.vector_embedding_provider}")

    TextEmbedding = _import_fastembed()
    _embedding_model = TextEmbedding(model_name=s.vector_embedding_model)
    return _embedding_model


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_embedding_model()
    vectors = []
    for vec in model.embed(texts):
        vectors.append(vec.tolist() if hasattr(vec, "tolist") else list(vec))
    return vectors


def _get_vector_size() -> int:
    global _vector_size
    if _vector_size is not None:
        return _vector_size
    probe = _embed_texts(["dimension probe"])
    if not probe:
        raise RuntimeError("FastEmbed 未返回向量")
    _vector_size = len(probe[0])
    return _vector_size


def ensure_collection(profile_id: int) -> str:
    client = _get_client()
    _, models = _import_qdrant()
    name = _collection_name(profile_id)
    vector_size = _get_vector_size()

    exists = False
    try:
        exists = bool(client.collection_exists(name))
    except AttributeError:
        try:
            client.get_collection(name)
            exists = True
        except Exception:
            exists = False

    if not exists:
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
    return name


def index_chunks(profile_id: int, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Upsert chunks into the profile collection.

    Each chunk dict must include chunk_id, document_id, content, and metadata.
    """
    if not chunks:
        return {"indexed": 0, "error": None}
    if not is_vector_available():
        return {"indexed": 0, "error": "vector unavailable"}

    client = _get_client()
    _, models = _import_qdrant()
    collection = ensure_collection(profile_id)
    texts = [str(c.get("content", "")) for c in chunks]
    vectors = _embed_texts(texts)

    points = []
    for chunk, vector in zip(chunks, vectors):
        chunk_id = int(chunk["chunk_id"])
        payload = {
            "profile_id": int(profile_id),
            "document_id": int(chunk["document_id"]),
            "chunk_id": chunk_id,
            "filename": chunk.get("filename", ""),
            "chunk_index": int(chunk.get("chunk_index", 0)),
            "parser": chunk.get("parser") or "builtin",
            "char_count": int(chunk.get("char_count", 0)),
            "created_at": str(chunk.get("created_at") or ""),
            "content": chunk.get("content", ""),
        }
        points.append(models.PointStruct(id=chunk_id, vector=vector, payload=payload))

    client.upsert(collection_name=collection, points=points)
    return {"indexed": len(points), "error": None, "collection": collection}


def search_chunks_vector(profile_id: int, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    """Search Qdrant by semantic similarity. Returns [] when unavailable."""
    if not query.strip() or not is_vector_available():
        return []

    s = get_settings()
    limit = top_k or s.vector_top_k
    client = _get_client()
    collection = ensure_collection(profile_id)
    query_vector = _embed_texts([query])[0]

    try:
        result = client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )
        points = getattr(result, "points", result)
    except AttributeError:
        points = client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,
        )

    items = []
    for point in points:
        payload = getattr(point, "payload", None) or {}
        score = getattr(point, "score", None)
        items.append({
            "content": payload.get("content", ""),
            "score": float(score or 0.0),
            "similarity_score": float(score or 0.0),
            "retrieval_method": "vector",
            "profile_id": payload.get("profile_id", profile_id),
            "document_id": payload.get("document_id"),
            "chunk_id": payload.get("chunk_id"),
            "filename": payload.get("filename", ""),
            "chunk_index": payload.get("chunk_index"),
            "parser": payload.get("parser", "builtin"),
            "char_count": payload.get("char_count", 0),
        })
    return items


def delete_document_vectors(profile_id: int, document_id: int) -> None:
    """Best-effort deletion for a document's vector points."""
    if not is_vector_available():
        return
    try:
        client = _get_client()
        _, models = _import_qdrant()
        collection = _collection_name(profile_id)
        selector = models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=int(document_id)),
                    )
                ]
            )
        )
        client.delete(collection_name=collection, points_selector=selector)
    except Exception as e:
        logger.warning("Vector delete skipped for profile=%s document=%s: %s", profile_id, document_id, e)


def collection_info(profile_id: int) -> dict[str, Any]:
    status = detect_vector()
    info: dict[str, Any] = {
        "collection": _collection_name(profile_id),
        "points_count": 0,
        "indexed": False,
    }
    if not status.available:
        return info
    try:
        client = _get_client()
        collection = _collection_name(profile_id)
        if hasattr(client, "collection_exists") and not client.collection_exists(collection):
            return info
        data = client.get_collection(collection)
        count = getattr(data, "points_count", None)
        info["points_count"] = int(count or 0)
        info["indexed"] = info["points_count"] > 0
    except Exception as e:
        info["error"] = str(e)
    return info
