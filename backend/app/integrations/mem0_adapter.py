from __future__ import annotations

"""
mem0 Adapter (SKELETON — not yet enabled)

mem0 is a memory layer for AI applications that provides long-term memory,
user preferences, and cross-session context. It's NOT installed by default.

When enabled, this adapter will:
1. Store important facts and preferences from conversations
2. Retrieve relevant memories for each chat turn
3. Update memories based on new information

Current MVP uses SQLite chat_messages for short-term history only.
"""

import logging

logger = logging.getLogger(__name__)


async def add_memory(user_id: str, content: str, metadata: dict = None) -> str:
    """Store a memory entry.

    Args:
        user_id: Identifier for the user/profile.
        content: Memory content to store.
        metadata: Optional metadata dict.

    Returns:
        Memory ID (when enabled).

    Raises:
        NotImplementedError: mem0 is not installed.
    """
    raise NotImplementedError(
        "mem0 is not installed. To enable long-term memory:\n"
        "1. Install mem0: pip install mem0ai\n"
        "2. Configure mem0 settings in .env\n"
        "3. Set MEM0_ENABLED=true\n"
        "See docs/integrations.md for detailed instructions."
    )


async def search_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """Search memories for a user.

    Args:
        user_id: Identifier for the user/profile.
        query: Search query.
        limit: Max results to return.

    Returns:
        List of memory entries.

    Raises:
        NotImplementedError: mem0 is not installed.
    """
    raise NotImplementedError(
        "mem0 is not installed. Install mem0ai to enable memory search."
    )
