from __future__ import annotations

"""
mem0 Adapter — optional long-term memory layer.

mem0 (mem0ai/mem0) provides persistent cross-session memory for AI applications.
It is NOT installed by default. When MEM0_ENABLED=false (default), the project
uses SQLite chat_messages for short-term history only.

Install: pip install mem0ai
Enable:  set MEM0_ENABLED=true in .env
Verify:  GET /api/integrations/mem0/status
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Known mem0 import paths and class names (API may vary across versions)
_MEM0_IMPORT_ATTEMPTS = [
    ("mem0", "Memory"),
    ("mem0ai", "Memory"),
    ("mem0", "MemoryClient"),
    ("mem0ai", "MemoryClient"),
]


@dataclass
class Mem0Status:
    installed: bool       # package is importable
    enabled: bool         # MEM0_ENABLED=true in .env
    available: bool       # installed AND client can be instantiated
    provider: str = "local"
    error: Optional[str] = None


def _get_config() -> dict:
    """Read mem0 config from env."""
    return {
        "enabled": os.getenv("MEM0_ENABLED", "false").lower() in ("1", "true", "yes"),
        "provider": os.getenv("MEM0_PROVIDER", "local"),
        "collection_prefix": os.getenv("MEM0_COLLECTION_PREFIX", "ai_clone_profile"),
    }


def _try_import_mem0() -> tuple[bool, Optional[str], Optional[type]]:
    """Try to import mem0 Memory class. Returns (ok, error, Memory_class)."""
    for module_name, class_name in _MEM0_IMPORT_ATTEMPTS:
        try:
            mod = __import__(module_name, fromlist=[class_name])
            cls = getattr(mod, class_name, None)
            if cls is not None:
                return True, None, cls
        except ImportError:
            continue
        except Exception as e:
            logger.debug(f"mem0 import attempt {module_name}.{class_name}: {e}")
            continue
    return False, "mem0ai not installed. Run: pip install mem0ai", None


def _try_init_client(memory_cls: type, cfg: dict) -> tuple[bool, Optional[str], Optional[object]]:
    """Try to instantiate a mem0 Memory client. Returns (ok, error, client)."""
    # Attempt 1: Memory.from_config(dict)  (mem0 v0.x common pattern)
    try:
        if hasattr(memory_cls, "from_config"):
            config = {
                "vector_store": {
                    "provider": cfg["provider"],
                    "config": {
                        "collection_name": cfg["collection_prefix"],
                    },
                },
            }
            client = memory_cls.from_config(config)
            return True, None, client
    except Exception as e:
        logger.debug(f"mem0 from_config failed: {e}")

    # Attempt 2: Memory() with no args (uses env vars)
    try:
        client = memory_cls()
        return True, None, client
    except Exception as e:
        logger.debug(f"mem0 default init failed: {e}")

    # Attempt 3: Memory(config_dict=...) keyword arg
    try:
        config = {
            "vector_store": {
                "provider": cfg["provider"],
                "config": {
                    "collection_name": cfg["collection_prefix"],
                },
            },
        }
        client = memory_cls(config=config)
        return True, None, client
    except Exception as e:
        logger.debug(f"mem0 config= init failed: {e}")

    return False, "mem0 installed but client init failed — API may have changed. Check mem0ai version.", None


def detect_mem0() -> Mem0Status:
    """Check if mem0 is installed, enabled, and API-compatible. Never raises."""
    cfg = _get_config()

    # Step 1: try import
    import_ok, import_err, memory_cls = _try_import_mem0()
    if not import_ok:
        return Mem0Status(
            installed=False,
            enabled=False,
            available=False,
            provider=cfg["provider"],
            error=import_err,
        )

    # Step 2: try client instantiation
    init_ok, init_err, _client = _try_init_client(memory_cls, cfg)
    if not init_ok:
        return Mem0Status(
            installed=True,
            enabled=cfg["enabled"],
            available=False,
            provider=cfg["provider"],
            error=init_err,
        )

    return Mem0Status(
        installed=True,
        enabled=cfg["enabled"],
        available=True,
        provider=cfg["provider"],
    )


# Cache the client + init status for the process lifetime
_client_cache: Optional[object] = None
_client_init_ok: bool = False
_client_init_attempted: bool = False


def _get_memory_client():
    """Get a configured mem0 Memory client, or None if unavailable.
    Caches the result after first attempt so we don't retry imports on every chat turn.
    """
    global _client_cache, _client_init_ok, _client_init_attempted

    if _client_init_attempted:
        return _client_cache if _client_init_ok else None

    _client_init_attempted = True
    cfg = _get_config()

    if not cfg["enabled"]:
        logger.debug("mem0: disabled by config (MEM0_ENABLED=false)")
        return None

    import_ok, _import_err, memory_cls = _try_import_mem0()
    if not import_ok:
        logger.debug("mem0: not installed")
        return None

    init_ok, init_err, client = _try_init_client(memory_cls, cfg)
    if not init_ok:
        logger.warning(f"mem0: {init_err}")
        return None

    _client_cache = client
    _client_init_ok = True
    logger.info("mem0: client initialized (provider=%s)", cfg["provider"])
    return client


def add_memory_sync(
    user_id: str,
    content: str,
    metadata: Optional[dict] = None,
) -> bool:
    """Store a memory entry synchronously. Returns True on success.

    user_id uses the format "profile_{profile_id}" to scope memories.
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

        # mem0 API may use add(content, user_id=..., metadata=...) or add(messages=[...])
        if hasattr(client, "add"):
            # Try keyword-arg style (common in mem0 v0.x)
            try:
                client.add(safe_content, user_id=user_id, metadata=safe_meta)
            except TypeError:
                # Maybe it expects a single dict argument
                client.add({"content": safe_content, "user_id": user_id, "metadata": safe_meta})
            logger.debug("mem0: add ok user_id=%s", user_id)
            return True

        logger.debug("mem0: client has no add() method")
        return False
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
        results = client.search(query, user_id=user_id, limit=limit)
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
            return {"stored": 0, "error": f"mem0 已安装但不可用: {status.error or 'API 兼容性问题'}"}
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
            # Store profile identity
            client.add(
                f"AI角色 {profile_name} 的长期记忆初始化。关系类型见metadata。",
                user_id=user_id,
                metadata={"type": "profile_identity", "name": profile_name},
            )
            stored += 1

            # Store style card excerpt
            if style_card:
                client.add(
                    style_card[:3000],
                    user_id=user_id,
                    metadata={"type": "style_card"},
                )
                stored += 1

            # Replay recent chat messages into mem0
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


# ── Async wrappers for FastAPI compatibility ──

async def add_memory(user_id: str, content: str, metadata: dict = None) -> bool:
    """Async wrapper around add_memory_sync."""
    return add_memory_sync(user_id, content, metadata)


async def search_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """Async wrapper around search_memory_sync."""
    return search_memory_sync(user_id, query, limit)
