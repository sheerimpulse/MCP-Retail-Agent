# retail_agent/memory.py
"""
mem0 integration for the retail support agent.

Provides a thin wrapper around the mem0 client so the rest of the codebase
never imports mem0 directly — making it easy to swap providers later.

Environment variables (add to your .env):
    MEM0_API_KEY   – required when using the managed mem0 cloud service
    MEM0_PROVIDER  – "cloud" (default) or "local"
                     "local" spins up an in-process Qdrant + SQLite store
                     (no API key needed, good for local dev / testing)
"""

from __future__ import annotations

import os
import sys
from typing import Any
from dotenv import load_dotenv
load_dotenv()

# ── lazy singleton ──────────────────────────────────────────────────────────
_client = None

def log(msg: str):
    """Safe logging for Memory — must use stderr, never stdout."""
    print(msg, file=sys.stderr)


def _get_client():
    global _client
    if _client is not None:
        return _client

    provider = os.getenv("MEM0_PROVIDER", "cloud").lower()

    try:
        if provider == "local":
            # Uses local Qdrant (in-memory) + SQLite — no API key required.
            # pip install mem0ai[local]  (pulls in qdrant-client)
            from mem0 import Memory

            config = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "retail_agent_memories",
                        "host": "localhost",
                        "port": 6333,
                        "embedding_model_dims": 1536,
                    },
                },
                "llm": {
                    "provider": "openai",          # mem0 uses this for extraction
                    "config": {"model": "gpt-4o-mini"},
                },
                "embedder": {
                    "provider": "openai",
                    "config": {"model": "text-embedding-3-small"},
                },
            }
            _client = Memory.from_config(config)
            print("[Memory] Initialised mem0 with LOCAL Qdrant store", file=sys.stderr)

        else:
            # Managed mem0 cloud — requires MEM0_API_KEY in env / .env
            from mem0 import MemoryClient

            api_key = os.getenv("MEM0_API_KEY")
            if not api_key:
                raise EnvironmentError(
                    "MEM0_API_KEY is not set. "
                    "Add it to your .env or set MEM0_PROVIDER=local for local dev."
                )
            _client = MemoryClient(api_key=api_key)
            print("[Memory] Initialised mem0 cloud client", file=sys.stderr)

    except ImportError as exc:
        print(
            f"[Memory] WARNING: mem0 import failed ({exc}). "
            "Memory features will be disabled. Run: pip install mem0ai",
            file=sys.stderr,
        )
        _client = _NoOpMemory()

    return _client


# ── public helpers ──────────────────────────────────────────────────────────

def save_memory(messages: list[dict], user_id: str, metadata: dict | None = None) -> None:
    log(f"SAVING MEMORY {messages}")
    """
    Persist a list of {role, content} messages as memories for *user_id*.

    Example
    -------
    save_memory(
        [{"role": "user", "content": "Customer prefers SMS contact."}],
        user_id="cust_001",
        metadata={"source": "get_customer"},
    )
    """
    client = _get_client()
    try:
        kwargs: dict[str, Any] = {"user_id": user_id}
        if metadata:
            kwargs["metadata"] = metadata
        client.add(messages, **kwargs)
        print(f"[Memory] Saved memory for user_id={user_id}", file=sys.stderr)
    except Exception as exc:
        print(f"[Memory] ERROR saving memory: {exc}", file=sys.stderr)


def search_memory(query: str, user_id: str, limit: int = 5) -> list[dict]:
    """
    Return up to *limit* relevant memories for *user_id* matching *query*.

    Returns a list of dicts, each with at least a ``memory`` key.
    """
    client = _get_client()
    try:
        results = client.search(query, filters={"user_id": user_id}, limit=limit)
        # mem0 cloud returns {"results": [...]}; local returns a list directly
        if isinstance(results, dict):
            results = results.get("results", [])
        print(
            f"[Memory] Retrieved {len(results)} memories for user_id={user_id}",
            file=sys.stderr,
        )
        return results
    except Exception as exc:
        print(f"[Memory] ERROR searching memory: {exc}", file=sys.stderr)
        return []


def format_memories_for_prompt(memories: list[dict]) -> str:
    """
    Convert raw mem0 results into a concise block suitable for injection
    into the agent's context / session state.
    """
    if not memories:
        return ""
    lines = ["=== Past customer context (from memory) ==="]
    for i, m in enumerate(memories, 1):
        text = m.get("memory") or m.get("text") or str(m)
        lines.append(f"{i}. {text}")
    lines.append("==========================================")
    return "\n".join(lines)


# ── no-op fallback (when mem0 is not installed) ─────────────────────────────

class _NoOpMemory:
    """Silent stub used when mem0ai is not installed."""

    def add(self, *args, **kwargs):
        return None

    def search(self, *args, **kwargs):
        return []