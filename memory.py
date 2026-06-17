"""Persistent scoped memory with JSON storage and semantic-ish retrieval."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Literal

from database import JsonDatabase

MemoryScope = Literal["users", "guilds", "channels", "global"]


@dataclass(slots=True)
class MemoryItem:
    text: str
    kind: str = "note"
    owner_id: str | None = None
    importance: int = 3
    id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.id:
            self.id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class MemoryStore:
    def __init__(self, db: JsonDatabase) -> None:
        self.db = db

    def remember(self, scope: MemoryScope, text: str, *, key: str | None = None, kind: str = "note", owner_id: str | None = None, importance: int = 3) -> MemoryItem:
        item = MemoryItem(text=text, kind=kind, owner_id=owner_id, importance=importance)
        def mutate(data: dict[str, Any]) -> None:
            bucket = data.setdefault("memory", {}).setdefault(scope, [] if scope == "global" else {})
            if scope == "global":
                bucket.append(asdict(item))
            else:
                if key is None:
                    raise ValueError(f"scope {scope} requires a key")
                bucket.setdefault(str(key), []).append(asdict(item))
        self.db.mutate(mutate)
        return item

    def save(self, scope: MemoryScope, item: MemoryItem, key: str | None = None) -> None:
        self.remember(scope, item.text, key=key, kind=item.kind, owner_id=item.owner_id, importance=item.importance)

    def update(self, memory_id: str, text: str, *, importance: int | None = None) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        def mutate(data: dict[str, Any]) -> None:
            nonlocal changed
            for entry in self._all_entries(data.setdefault("memory", {})):
                if entry.get("id") == memory_id:
                    entry["text"] = text
                    entry["updated_at"] = now
                    if importance is not None:
                        entry["importance"] = importance
                    changed = True
        self.db.mutate(mutate)
        return changed

    def forget(self, query_or_id: str, *, scope: MemoryScope | None = None, key: str | None = None) -> int:
        removed = 0
        def keep(entry: dict[str, Any]) -> bool:
            nonlocal removed
            matched = entry.get("id") == query_or_id or query_or_id.lower() in str(entry.get("text", "")).lower()
            if matched:
                removed += 1
            return not matched
        def mutate(data: dict[str, Any]) -> None:
            memory = data.setdefault("memory", {})
            scopes: list[MemoryScope] = [scope] if scope else ["users", "guilds", "channels", "global"]
            for scope_name in scopes:
                bucket = memory.setdefault(scope_name, [] if scope_name == "global" else {})
                if scope_name == "global":
                    memory[scope_name] = [entry for entry in bucket if keep(entry)]
                elif key is not None:
                    bucket[str(key)] = [entry for entry in bucket.get(str(key), []) if keep(entry)]
                else:
                    for bucket_key, entries in list(bucket.items()):
                        bucket[bucket_key] = [entry for entry in entries if keep(entry)]
        self.db.mutate(mutate)
        return removed

    def search(self, query: str, *, scope: MemoryScope | None = None, key: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        memory = self.db.get("memory", default={})
        scopes: list[MemoryScope] = [scope] if scope else ["users", "guilds", "channels", "global"]
        candidates: list[dict[str, Any]] = []
        for scope_name in scopes:
            for entry in self._entries_for(memory, scope_name, key):
                text = str(entry.get("text", ""))
                lexical = 1.0 if query.lower() in text.lower() else 0.0
                overlap = len(set(query.lower().split()) & set(text.lower().split())) / max(1, len(set(query.lower().split())))
                semantic = SequenceMatcher(None, query.lower(), text.lower()).ratio()
                candidates.append({**entry, "scope": scope_name, "score": lexical + overlap + semantic + int(entry.get("importance", 3)) / 10})
        return sorted(candidates, key=lambda item: item["score"], reverse=True)[:limit]

    def size(self) -> int:
        return len(self._all_entries(self.db.get("memory", default={})))

    def _entries_for(self, memory: dict[str, Any], scope: MemoryScope, key: str | None) -> list[dict[str, Any]]:
        bucket = memory.get(scope, [] if scope == "global" else {})
        if scope == "global":
            return list(bucket)
        if key is not None:
            return list(bucket.get(str(key), []))
        return [entry for entries in bucket.values() for entry in entries]

    def _all_entries(self, memory: dict[str, Any]) -> list[dict[str, Any]]:
        entries = list(memory.get("global", []))
        for scope in ("users", "guilds", "channels"):
            entries.extend(entry for values in memory.get(scope, {}).values() for entry in values)
        return entries
