from __future__ import annotations

"""
mem0 Adapter — optional long-term memory layer.

mem0 (mem0ai/mem0) provides persistent cross-session memory for AI applications.
It is NOT installed by default. When MEM0_ENABLED=false (default), the project
uses SQLite chat_messages for short-term history only.

Install: pip install mem0ai
Enable:  set MEM0_ENABLED=true in .env
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Mem0Status:
    installed: bool
    enabled: bool
    provider: str = "local"
    error: Optional[str] = None


def _get_config() -> dict:
    """Read mem0 config from env, never logging sensitive values."""
    return {
        "enabled": os.getenv("MEM0_ENABLED", "false").lower() in ("1", "true", "yes"),
        "provider": os.getenv("MEM0_PROVIDER", "local"),
        "collection_prefix": os.getenv("MEM0_COLLECTION_PREFIX", "ai_clone_profile"),
    }


def detect_mem0() -> Mem0Status:
    """Check if mem0 is installed and configured. Never raises."""
    cfg = _get_config()
    try:
        import mem0  # noqa: F401
        return Mem0Status(
            installed=True,
            enabled=cfg["enabled"],
            provider=cfg["provider"],
        )
    except ImportError:
        return Mem0Status(
            installed=False,
            enabled=False,
            provider=cfg["provider"],
            error="mem0ai not installed. Run: pip install mem0ai",
        )
    except Exception as e:
        logger.warning(f"mem0 detection error: {e}")
        return Mem0Status(
            installed=False,
            enabled=False,
            provider=cfg["provider"],
            error=str(e),
        )


def _get_memory_client():
    """Get a configured mem0 Memory client, or None if unavailable."""
    cfg = _get_config()
    if not cfg["enabled"]:
        return None
    try:
        from mem0 import Memory
        # Use local provider by default (stores in local SQLite/vector DB)
        # API keys are read from env by mem0 itself, we never pass them explicitly
        config = {
            "vector_store": {
                "provider": cfg["provider"],
                "config": {
                    "collection_name": cfg["collection_prefix"],
                },
            },
        }
        return Memory.from_config(config)
    except ImportError:
        logger.debug("mem0 not installed, using SQLite fallback")
        return None
    except Exception as e:
        logger.warning(f"mem0 client init failed, using SQLite fallback: {e}")
        return None


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
        # sanitize metadata — never log API keys or full messages
        safe_meta = {}
        if metadata:
            safe_meta = {
                k: (v[:200] if isinstance(v, str) and len(v) > 200 else v)
                for k, v in metadata.items()
                if k not in ("api_key", "token", "password", "secret")
            }
        # Truncate content to avoid storing enormous single memories
        safe_content = content[:4000] if len(content) > 4000 else content
        client.add(safe_content, user_id=user_id, metadata=safe_meta)
        logger.debug(f"mem0: stored memory for user_id={user_id}")
        return True
    except Exception as e:
        logger.warning(f"mem0 add failed (falling back to SQLite): {e}")
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
        # Normalize results to list of dicts
        if isinstance(results, list):
            return [
                {
                    "id": getattr(r, "id", ""),
                    "memory": getattr(r, "memory", str(r)),
                    "score": getattr(r, "score", None),
                }
                for r in results
            ]
        return []
    except Exception as e:
        logger.warning(f"mem0 search failed (falling back to empty): {e}")
        return []


def rebuild_memories_sync(profile_id: int, profile_name: str, style_card: str = "") -> dict:
    """Rebuild mem0 memories from existing chat history and analysis.

    Returns {"stored": N, "error": None} or {"stored": 0, "error": "..."}.
    Does NOT raise — failures are reported in the return dict.
    """
    client = _get_memory_client()
    if client is None:
        return {"stored": 0, "error": "mem0 not available or not enabled"}

    try:
        from app.models.session import SessionLocal
        from app.models.database import ChatMessage, AnalysisReport
    except ImportError as e:
        return {"stored": 0, "error": f"Database import failed: {e}"}

    user_id = f"profile_{profile_id}"
    stored = 0

    try:
        db = SessionLocal()
        try:
            # Store profile identity
            client.add(
                f"这是关于 {profile_name} 的 AI 模拟角色的长期记忆。角色基于上传资料生成。",
                user_id=user_id,
                metadata={"type": "identity", "profile_name": profile_name},
            )
            stored += 1

            # Store style card as memory
            if style_card:
                client.add(
                    f"风格卡: {style_card[:3000]}",
                    user_id=user_id,
                    metadata={"type": "style_card"},
                )
                stored += 1

            # Store recent chat messages as memories
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.profile_id == profile_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(50)
                .all()
            )
            for msg in reversed(messages):
                role_label = "用户" if msg.role == "user" else "AI角色"
                client.add(
                    f"{role_label}: {msg.content[:2000]}",
                    user_id=user_id,
                    metadata={"type": "chat", "role": msg.role},
                )
                stored += 1

            logger.info(f"mem0: rebuilt {stored} memories for profile {profile_id}")
            return {"stored": stored, "error": None}
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"mem0 rebuild failed: {e}")
        return {"stored": stored, "error": str(e)}


# ── Async wrappers for FastAPI compatibility ──

async def add_memory(user_id: str, content: str, metadata: dict = None) -> bool:
    """Async wrapper around add_memory_sync."""
    return add_memory_sync(user_id, content, metadata)


async def search_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """Async wrapper around search_memory_sync."""
    return search_memory_sync(user_id, query, limit)
