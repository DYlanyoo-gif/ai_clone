from __future__ import annotations

"""
mem0 Adapter — optional long-term memory layer.

mem0 (mem0ai/mem0) provides persistent cross-session memory for AI applications.
It is NOT installed by default. When MEM0_ENABLED=false (default), the project
uses SQLite chat_messages for short-term history only.

Install: pip install mem0ai
Enable:  set MEM0_ENABLED=true in .env
Verify:  GET /api/integrations/mem0/status

mem0ai 2.0.4 requires:
  - A vector store (Qdrant local mode works out of the box)
  - An LLM (DeepSeek is supported)
  - An embedding service (OpenAI API Key required — DeepSeek does NOT provide embeddings)
If any piece is missing, mem0 returns available=false with a specific error message.
The project falls back to SQLite chat_messages automatically.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Mem0Status:
    installed: bool       # package is importable
    enabled: bool         # MEM0_ENABLED=true in .env
    available: bool       # installed AND client can be instantiated
    provider: str = "local"
    error: Optional[str] = None


# ── Module-level cache — client is created ONCE per process ──
# Multiple Qdrant instances on the same path cause file-lock conflicts on Windows.
_client: Optional[object] = None
_init_ok: bool = False
_init_error: Optional[str] = None
_init_attempted: bool = False
_imported_class: Optional[type] = None


def _get_config() -> dict:
    """Read mem0 config from env."""
    return {
        "enabled": os.getenv("MEM0_ENABLED", "false").lower() in ("1", "true", "yes"),
        "provider": os.getenv("MEM0_PROVIDER", "local"),
        "collection_prefix": os.getenv("MEM0_COLLECTION_PREFIX", "ai_clone_profile"),
    }


# ── Single initialization path (used by both detect_mem0 and _get_memory_client) ──

def _ensure_initialized() -> tuple[bool, Optional[object], Optional[str]]:
    """Initialize mem0 client if not already done. Caches result globally.
    Returns (ok, client_or_None, error_or_None).
    """
    global _client, _init_ok, _init_error, _init_attempted, _imported_class

    if _init_attempted:
        return _init_ok, _client, _init_error

    _init_attempted = True
    cfg = _get_config()

    # Step 1: import
    for module_name, class_name in [("mem0", "Memory"), ("mem0", "MemoryClient")]:
        try:
            mod = __import__(module_name, fromlist=[class_name])
            _imported_class = getattr(mod, class_name, None)
            if _imported_class is not None:
                break
        except ImportError:
            continue
        except Exception as e:
            logger.debug("mem0 import %s.%s: %s", module_name, class_name, e)
            continue

    if _imported_class is None:
        _init_error = "mem0ai not installed. Run: pip install mem0ai"
        return False, None, _init_error

    # Step 2: build config and instantiate
    data_dir = os.path.abspath(os.path.join(os.getcwd(), "..", "data"))
    os.makedirs(data_dir, exist_ok=True)
    llm_api_key = os.getenv("LLM_API_KEY", "")
    # Embeddings MUST use a real OpenAI-compatible embedding key.
    # DeepSeek API key does NOT work for OpenAI embeddings (different service).
    # Do NOT fall back to LLM_API_KEY — causes 401 errors at runtime.
    embedding_api_key = os.getenv("OPENAI_API_KEY", "") or os.getenv("EMBEDDING_API_KEY", "")
    embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")

    # Attempt: from_config with Qdrant local + DeepSeek LLM + OpenAI embedder
    # Check preconditions before attempting init (so available=false is immediate)
    if not embedding_api_key:
        _init_error = (
            "mem0 2.0.4 需要 OpenAI API Key 用于向量嵌入（DeepSeek 不提供 embeddings API）。"
            "请在 .env 中设置 OPENAI_API_KEY=sk-... 并重启后端。"
        )
        return False, None, _init_error

    if hasattr(_imported_class, "from_config"):
        config_dict = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": cfg["collection_prefix"],
                    "path": os.path.join(data_dir, "mem0_qdrant"),
                    "on_disk": True,
                    "embedding_model_dims": 1536,
                },
            },
            "llm": {
                "provider": "deepseek",
                "config": {
                    "model": os.getenv("ANALYSIS_MODEL", "deepseek-chat"),
                    "api_key": llm_api_key,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": embedding_api_key,
                    "openai_base_url": embedding_base_url,
                },
            },
            "history_db_path": os.path.join(data_dir, "mem0_history.db"),
        }
        try:
            _client = _imported_class.from_config(config_dict)
            _init_ok = True
            logger.info("mem0: client initialized — qdrant+deepseek+openai-embeddings")
            return True, _client, None
        except Exception as e:
            err_str = str(e)
            if any(kw in err_str.lower() for kw in ("api_key", "openai", "credential", "embed")):
                _init_error = (
                    "mem0 2.0.4 缺少 embedding 服务：需要 OpenAI API Key 用于向量嵌入。"
                    "请设置环境变量 OPENAI_API_KEY（推荐），或 EMBEDDING_API_KEY。"
                    f"（原始错误: {err_str[:150]}）"
                )
                return False, None, _init_error
            # Other config error — e.g. missing model, vector store path issue
            _init_error = f"mem0 初始化失败: {err_str[:300]}"
            return False, None, _init_error

    # Attempt: MemoryClient with API key (mem0 cloud)
    try:
        mem0_api_key = os.getenv("MEM0_API_KEY", "")
        if mem0_api_key:
            _client = _imported_class(api_key=mem0_api_key)
            _init_ok = True
            logger.info("mem0: client initialized — cloud MemoryClient")
            return True, _client, None
    except Exception as e:
        logger.debug("mem0 cloud init failed: %s", e)

    _init_error = (
        "mem0 2.0.4 初始化失败：缺少 embedding 服务。"
        "mem0 需要 OpenAI API Key（用于向量嵌入），DeepSeek 不提供此服务。"
        "解决方案: 在 .env 中设置 OPENAI_API_KEY=sk-... 并重启后端。"
    )
    return False, None, _init_error


# ── Public API ──

def detect_mem0() -> Mem0Status:
    """Check if mem0 is installed, enabled, and API-compatible. Never raises."""
    cfg = _get_config()

    # Force re-init for status checks (so users see fresh results after config changes)
    # Only force if not already attempted to avoid Qdrant lock issues on repeated calls
    ok, _client_ref, error = _ensure_initialized()

    if not _init_attempted:
        # Should not happen — _ensure_initialized always sets _init_attempted
        return Mem0Status(installed=False, enabled=False, available=False, provider=cfg["provider"],
                          error="Internal error: init not attempted")

    installed = _imported_class is not None

    return Mem0Status(
        installed=installed,
        enabled=cfg["enabled"],
        available=ok,
        provider=cfg["provider"],
        error=error if not ok else None,
    )


def _get_memory_client():
    """Get the cached mem0 Memory client, or None if unavailable."""
    if not _init_attempted:
        _ensure_initialized()
    return _client if _init_ok else None


def add_memory_sync(
    user_id: str,
    content: str,
    metadata: Optional[dict] = None,
) -> bool:
    """Store a memory entry synchronously. Returns True on success.
    Falls back silently on any error — never breaks the chat flow.
    """
    client = _get_memory_client()
    if client is None:
        return False
    try:
        safe_content = content[:4000] if len(content) > 4000 else content
        safe_meta: dict = {}
        if metadata:
            safe_meta = {
                k: (v[:200] if isinstance(v, str) and len(v) > 200 else v)
                for k, v in metadata.items()
                if k not in ("api_key", "token", "password", "secret")
            }
        try:
            client.add(safe_content, user_id=user_id, metadata=safe_meta)
        except TypeError:
            client.add({"content": safe_content, "user_id": user_id, "metadata": safe_meta})
        logger.debug("mem0: add ok user_id=%s", user_id)
        return True
    except Exception as e:
        logger.warning("mem0 add failed (falling back to SQLite): %s", e)
        return False


def search_memory_sync(
    user_id: str,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Search memories for a user synchronously. Returns list of memory entries.
    Falls back to empty list on any error — never breaks the chat flow.
    """
    client = _get_memory_client()
    if client is None:
        return []
    try:
        # mem0 v2.x search() uses filters=, not user_id= directly
        try:
            results = client.search(query, user_id=user_id, limit=limit)
        except TypeError:
            # mem0 v2.0.4+: user_id moved to filters
            results = client.search(query, filters={"user_id": user_id}, limit=limit)
        if results is None:
            return []
        if isinstance(results, list):
            normalized = []
            for r in results:
                if isinstance(r, dict):
                    normalized.append({
                        "id": r.get("id", ""),
                        "memory": r.get("memory", r.get("content", str(r))),
                        "score": r.get("score"),
                    })
                else:
                    normalized.append({
                        "id": getattr(r, "id", ""),
                        "memory": getattr(r, "memory", str(r)),
                        "score": getattr(r, "score", None),
                    })
            logger.debug("mem0: search ok user_id=%s results=%d", user_id, len(normalized))
            return normalized
        return []
    except Exception as e:
        logger.warning("mem0 search failed (falling back to empty): %s", e)
        return []


def rebuild_memories_sync(profile_id: int, profile_name: str, style_card: str = "") -> dict:
    """Rebuild mem0 memories from existing chat history and analysis.

    Returns {"stored": N, "error": None} or {"stored": 0, "error": "..."}.
    Does NOT raise — failures are reported in the return dict.
    """
    cfg = _get_config()
    if not cfg["enabled"]:
        return {"stored": 0, "error": "mem0 未启用。请在 .env 中设置 MEM0_ENABLED=true 并重启后端。"}

    client = _get_memory_client()
    if client is None:
        status = detect_mem0()
        if not status.installed:
            return {"stored": 0, "error": "mem0 未安装。请运行: pip install mem0ai"}
        if not status.available:
            return {"stored": 0, "error": f"mem0 已安装但不可用: {status.error or '未知错误'}"}
        return {"stored": 0, "error": "mem0 客户端初始化失败"}

    try:
        from app.models.session import SessionLocal
        from app.models.database import ChatMessage
    except ImportError as e:
        return {"stored": 0, "error": f"数据库导入失败: {e}"}

    user_id = f"profile_{profile_id}"
    stored = 0

    try:
        db = SessionLocal()
        try:
            client.add(
                f"AI角色 {profile_name} 的长期记忆初始化。",
                user_id=user_id,
                metadata={"type": "profile_identity", "name": profile_name},
            )
            stored += 1

            if style_card:
                client.add(
                    style_card[:3000],
                    user_id=user_id,
                    metadata={"type": "style_card"},
                )
                stored += 1

            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.profile_id == profile_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(100)
                .all()
            )
            for msg in reversed(messages):
                role_prefix = "用户说" if msg.role == "user" else "AI回复"
                client.add(
                    f"{role_prefix}: {msg.content[:1500]}",
                    user_id=user_id,
                    metadata={"type": "chat_message", "role": msg.role},
                )
                stored += 1

            logger.info("mem0: rebuilt %d memories for profile %d", stored, profile_id)
            return {"stored": stored, "error": None}
        finally:
            db.close()
    except Exception as e:
        logger.warning("mem0 rebuild failed for profile %d: %s", profile_id, e)
        return {"stored": stored, "error": str(e)}


# ── Async wrappers ──

async def add_memory(user_id: str, content: str, metadata: dict = None) -> bool:
    return add_memory_sync(user_id, content, metadata)


async def search_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    return search_memory_sync(user_id, query, limit)
