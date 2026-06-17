"""Structured tool framework for INC0G."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from commands import DiscordObjectManager
from filesystem import FileSystemAwareness
from memory import MemoryStore
from services import ProviderManager
from websearch import WebSearchClient

ToolHandler = Callable[..., Awaitable[Any] | Any]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    handler: ToolHandler
    requires_permission: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self.usage: dict[str, int] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def run(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        self.usage[name] = self.usage.get(name, 0) + 1
        result = self._tools[name].handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


def build_default_tools(fs: FileSystemAwareness, memory: MemoryStore, providers: ProviderManager, discord_manager: DiscordObjectManager, web: WebSearchClient) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("read_file", "Read a safe project file", lambda path: fs.read(path)))
    registry.register(Tool("write_file", "Write a project file except credentials", lambda path, content: fs.write(path, content)))
    registry.register(Tool("list_files", "List project files", lambda: fs.scan()))
    registry.register(Tool("search_files", "Search safe project files", lambda query: fs.search(query)))
    registry.register(Tool("save_memory", "Save scoped memory", lambda scope, text, key=None, kind="note", owner_id=None, importance=3: memory.remember(scope, text, key=key, kind=kind, owner_id=owner_id, importance=importance)))
    registry.register(Tool("search_memory", "Search scoped memory", lambda query, scope=None, key=None, limit=5: memory.search(query, scope=scope, key=key, limit=limit)))
    registry.register(Tool("forget_memory", "Forget scoped memory by id or text", lambda query_or_id, scope=None, key=None: memory.forget(query_or_id, scope=scope, key=key)))
    registry.register(Tool("web_search", "Search the web and return citation-ready results", lambda query, limit=5: web.search(query, limit=limit)))
    registry.register(Tool("provider_status", "Inspect provider usage and health", lambda: providers.usage_report()))
    registry.register(Tool("create_channel", "Create a Discord text channel", discord_manager.create_text_channel, "manage_channels"))
    registry.register(Tool("create_role", "Create a Discord role", discord_manager.create_role, "manage_roles"))
    registry.register(Tool("create_thread", "Create a Discord thread", discord_manager.create_thread))
    registry.register(Tool("post_message", "Post a Discord message", discord_manager.post_message))
    registry.register(Tool("create_webhook", "Create a Discord webhook", discord_manager.create_webhook, "manage_webhooks"))
    return registry
