"""Request analysis and optimized prompt construction for INC0G."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from filesystem import FileSystemAwareness
from memory import MemoryStore

SEARCH_TRIGGERS = {"latest", "today", "recent", "current", "news", "research", "search", "look up", "rate limits", "2026"}
FILE_TRIGGERS = {"file", "code", "project", "bug", "implement", "refactor", "python", ".py", "data.json", "skill.txt"}


@dataclass(slots=True)
class RequestContext:
    prompt: str
    needs_web_search: bool = False
    needs_files: bool = False
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    relevant_files: dict[str, str] = field(default_factory=dict)
    discord_state: dict[str, Any] = field(default_factory=dict)


class ContextManager:
    def __init__(self, fs: FileSystemAwareness, memory: MemoryStore) -> None:
        self.fs = fs
        self.memory = memory

    def analyze(self, prompt: str) -> dict[str, bool]:
        lowered = prompt.lower()
        return {
            "needs_web_search": any(trigger in lowered for trigger in SEARCH_TRIGGERS),
            "needs_files": any(trigger in lowered for trigger in FILE_TRIGGERS),
        }

    def build(self, prompt: str, *, guild: Any = None, channel: Any = None, author: Any = None) -> RequestContext:
        analysis = self.analyze(prompt)
        user_key = str(getattr(author, "id", "")) if author else None
        guild_key = str(getattr(guild, "id", "")) if guild else None
        channel_key = str(getattr(channel, "id", "")) if channel else None
        memories: list[dict[str, Any]] = []
        for scope, key in (("users", user_key), ("guilds", guild_key), ("channels", channel_key), ("global", None)):
            if scope == "global" or key:
                memories.extend(self.memory.search(prompt, scope=scope, key=key, limit=3))
        files: dict[str, str] = {}
        if analysis["needs_files"]:
            for rel in self._select_files(prompt):
                content = self.fs.read(rel)
                files[rel] = content[:4000]
        return RequestContext(
            prompt=prompt,
            needs_web_search=analysis["needs_web_search"],
            needs_files=analysis["needs_files"],
            relevant_memories=memories[:8],
            relevant_files=files,
            discord_state={
                "guild": getattr(guild, "name", None),
                "guild_id": getattr(guild, "id", None),
                "channel": getattr(channel, "name", None),
                "channel_id": getattr(channel, "id", None),
                "author": getattr(author, "display_name", None),
                "author_id": getattr(author, "id", None),
            },
        )

    def _select_files(self, prompt: str) -> list[str]:
        lowered = prompt.lower()
        files = self.fs.scan(("*.py", "*.txt", "*.json", "requirements.txt"))
        selected = [path for path in files if Path(path).name.lower() in lowered or path.lower() in lowered]
        if selected:
            return selected[:5]
        hits = self.fs.search(prompt.split()[0]) if prompt.split() else {}
        selected.extend(hits.keys())
        return (selected or [path for path in files if path.endswith(".py")])[:5]
