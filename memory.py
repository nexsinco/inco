"""Persistent memory system with lightweight semantic retrieval."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Literal

from database import JsonDatabase

MemoryScope = Literal["users", "guilds", "channels", "tasks", "global"]


@dataclass(slots=True)
class MemoryItem:
    text: str
    kind: str = "note"
    owner_id: str | None = None
    created_at: str = ""
    importance: int = 3

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, db: JsonDatabase) -> None:
        self.db = db

    def save(self, scope: MemoryScope, item: MemoryItem, key: str | None = None) -> None:
        def mutate(data: dict[str, Any]) -> None:
            memory = data.setdefault("memory", {})
            bucket = memory.setdefault(scope, [] if scope == "global" else {})
            payload = asdict(item)
            if scope == "global":
                bucket.append(payload)
            else:
                if key is None:
                    raise ValueError(f"scope {scope} requires a key")
                bucket.setdefault(str(key), []).append(payload)
        self.db.mutate(mutate)

    def search(self, query: str, *, scope: MemoryScope | None = None, key: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        memory = self.db.get("memory", default={})
        scopes = [scope] if scope else ["users", "guilds", "channels", "tasks", "global"]
        for scope_name in scopes:
            bucket = memory.get(scope_name, [] if scope_name == "global" else {})
            if scope_name == "global":
                entries = bucket
            elif key is not None:
                entries = bucket.get(str(key), [])
            else:
                entries = [entry for values in bucket.values() for entry in values]
            for entry in entries:
                text = entry.get("text", "")
                lexical = 1.0 if query.lower() in text.lower() else 0.0
                semantic = SequenceMatcher(None, query.lower(), text.lower()).ratio()
                candidates.append({**entry, "scope": scope_name, "score": lexical + semantic + entry.get("importance", 3) / 10})
        return sorted(candidates, key=lambda item: item["score"], reverse=True)[:limit]

    def size(self) -> int:
        memory = self.db.get("memory", default={})
        total = len(memory.get("global", []))
        for scope in ("users", "guilds", "channels", "tasks"):
            total += sum(len(items) for items in memory.get(scope, {}).values())
        return total
