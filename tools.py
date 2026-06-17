"""Modular tool framework for INC0G."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from filesystem import FileSystemAwareness
from memory import MemoryItem, MemoryStore
from services import ProviderManager

ToolHandler = Callable[..., Awaitable[Any] | Any]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def run(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        result = self._tools[name].handler(**kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result


def build_default_tools(fs: FileSystemAwareness, memory: MemoryStore, providers: ProviderManager) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("file_reader", "Read safe project files", lambda path: fs.read(path)))
    registry.register(Tool("file_writer", "Write project files except credentials", lambda path, content: fs.write(path, content)))
    registry.register(Tool("directory_scanner", "Scan project structure", lambda: fs.scan()))
    registry.register(Tool("memory_search", "Search persistent semantic memory", lambda query: memory.search(query)))
    registry.register(Tool("memory_save", "Save persistent memory", lambda scope, text, key=None: memory.save(scope, MemoryItem(text=text), key)))
    registry.register(Tool("provider_manager", "Inspect provider health and usage", lambda: providers.usage_report()))
    registry.register(Tool("discord_manager", "Manage Discord guild objects via commands", lambda: "Use DiscordObjectManager methods from commands.py"))
    registry.register(Tool("role_manager", "Create, edit, and delete roles", lambda: "Role operations require manage_roles permission"))
    registry.register(Tool("channel_manager", "Create, edit, and delete channels", lambda: "Channel operations require manage_channels permission"))
    registry.register(Tool("thread_manager", "Create and manage threads", lambda: "Thread operations require thread permissions"))
    registry.register(Tool("message_manager", "Post, edit, and delete messages", lambda: "Message operations require channel permissions"))
    return registry
