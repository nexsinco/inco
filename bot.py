"""INC0G Discord AI operating system core."""
from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any

try:
    import discord
    from discord.ext import commands
except ImportError:  # pragma: no cover
    discord = None
    commands = None

from commands import DiscordObjectManager, setup_commands
from context import ContextManager, RequestContext
from database import JsonDatabase
from filesystem import FileSystemAwareness
from memory import MemoryStore
from services import ProviderManager
from tools import ToolRegistry, build_default_tools
from websearch import WebSearchClient

LOGGER = logging.getLogger("inc0g.bot")

SYSTEM_PROMPT = """You are INC0G, a production Discord AI operating system.
Behave like a modern conversational assistant: natural, precise, useful, and professional.
Before answering, use the supplied optimized context, memory, tool results, Discord state, and web citations.
Never reveal credentials, API keys, tokens, environment variables, or credentials.txt contents.
Respect Discord permissions. Explain limitations and failures clearly. If web results are provided, cite them by URL.
"""


class IncogRuntime:
    def __init__(self, root: str = ".") -> None:
        self.db = JsonDatabase("data.json")
        self.fs = FileSystemAwareness(root)
        self.memory = MemoryStore(self.db)
        self.providers = ProviderManager()
        self.discord_manager = DiscordObjectManager()
        self.web = WebSearchClient()
        self.tools: ToolRegistry = build_default_tools(self.fs, self.memory, self.providers, self.discord_manager, self.web)
        self.context = ContextManager(self.fs, self.memory)

    def state(self, guild: Any = None, channel: Any = None) -> dict[str, Any]:
        return {
            "provider": self.providers.current_provider.name,
            "memory_size": self.memory.size(),
            "guild": getattr(guild, "name", None),
            "channel": getattr(channel, "name", None),
            "tools": self.tools.names(),
            "provider_usage": self.providers.usage_report(),
        }

    async def answer(self, prompt: str, ctx: Any = None) -> str:
        guild = getattr(ctx, "guild", None)
        channel = getattr(ctx, "channel", None)
        author = getattr(ctx, "author", None)
        request_context = self.context.build(prompt, guild=guild, channel=channel, author=author)
        tool_results = await self._run_automatic_tools(prompt, request_context, ctx)
        messages = self._build_messages(prompt, request_context, tool_results)
        try:
            self.db.update_metric("commands")
            response = await self.providers.complete(messages)
            self._persist_usage_metrics()
            return response
        except Exception as exc:  # noqa: BLE001 - Discord agents must recover gracefully
            LOGGER.exception("INC0G failed to answer")
            self.db.update_metric("errors")
            return f"INC0G could not complete the request because all configured AI providers failed or are unavailable: {exc}"

    async def _run_automatic_tools(self, prompt: str, request_context: RequestContext, ctx: Any = None) -> dict[str, Any]:
        lowered = prompt.lower().strip()
        results: dict[str, Any] = {}
        author = getattr(ctx, "author", None)
        guild = getattr(ctx, "guild", None)
        channel = getattr(ctx, "channel", None)
        if lowered.startswith("remember ") or "remember that" in lowered:
            fact = re.sub(r"^remember\s+(that\s+)?", "", prompt, flags=re.IGNORECASE).strip()
            item = self.memory.remember("users", fact, key=str(getattr(author, "id", "global")), owner_id=str(getattr(author, "id", "")), kind="preference")
            results["save_memory"] = {"id": item.id, "text": item.text}
        if lowered.startswith("forget "):
            query = re.sub(r"^forget\s+", "", prompt, flags=re.IGNORECASE).strip()
            results["forget_memory"] = self.memory.forget(query, scope="users", key=str(getattr(author, "id", "global")))
        if request_context.needs_web_search:
            try:
                search_results = await self.web.search(prompt, limit=5)
                results["web_search"] = [asdict(result) for result in search_results]
            except Exception as exc:  # noqa: BLE001 - search outages should not crash Discord commands
                LOGGER.warning("Web search failed: %s", exc)
                results["web_search_error"] = str(exc)
        if guild is not None and "create channel" in lowered:
            match = re.search(r"create (?:a )?(?:text )?channel named ([\w\- ]+)", lowered)
            if match:
                name = match.group(1).strip().replace(" ", "-")[:90]
                created = await self.discord_manager.create_text_channel(guild, name, author)
                results["create_channel"] = {"id": getattr(created, "id", None), "name": getattr(created, "name", name)}
        if guild is not None and "create role" in lowered:
            match = re.search(r"create (?:a )?role named ([\w\- ]+)", lowered)
            if match:
                name = match.group(1).strip()[:90]
                created = await self.discord_manager.create_role(guild, name, author)
                results["create_role"] = {"id": getattr(created, "id", None), "name": getattr(created, "name", name)}
        if channel is not None and "create thread" in lowered:
            match = re.search(r"create (?:a )?thread named ([\w\- ]+)", lowered)
            if match:
                name = match.group(1).strip()[:90]
                created = await self.discord_manager.create_thread(channel, name)
                results["create_thread"] = {"id": getattr(created, "id", None), "name": getattr(created, "name", name)}
        return results

    def _build_messages(self, prompt: str, context: RequestContext, tool_results: dict[str, Any]) -> list[dict[str, str]]:
        optimized_context = {
            "discord_state": context.discord_state,
            "relevant_memory": context.relevant_memories,
            "relevant_files": context.relevant_files,
            "tool_results": tool_results,
            "available_tools": self.tools.names(),
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"User request: {prompt}\nOptimized context: {optimized_context}"},
        ]

    def _persist_usage_metrics(self) -> None:
        def mutate(data: dict[str, Any]) -> None:
            data.setdefault("metrics", {})["providers"] = self.providers.usage_report()
            data.setdefault("metrics", {})["tool_usage"] = self.tools.usage
            data.setdefault("metrics", {})["memory_items"] = self.memory.size()
        self.db.mutate(mutate)


if commands is not None:
    class IncogBot(commands.Bot):
        def __init__(self, runtime: IncogRuntime, **kwargs: Any) -> None:
            intents = kwargs.pop("intents", discord.Intents.default())
            intents.message_content = True
            intents.guilds = True
            intents.members = True
            super().__init__(command_prefix=kwargs.pop("command_prefix", "!"), intents=intents, **kwargs)
            self.runtime = runtime
            setup_commands(self)

        def incog_state(self, ctx: Any = None) -> dict[str, Any]:
            return self.runtime.state(getattr(ctx, "guild", None), getattr(ctx, "channel", None))

        async def answer(self, prompt: str, ctx: Any = None) -> str:
            return await self.runtime.answer(prompt, ctx=ctx)

        async def on_ready(self) -> None:
            LOGGER.info("INC0G connected as %s", self.user)
else:
    IncogBot = None  # type: ignore[assignment]
