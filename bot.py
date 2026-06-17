"""INC0G Discord AI operating system core."""
from __future__ import annotations

import logging
from typing import Any

try:
    import discord
    from discord.ext import commands
except ImportError:  # pragma: no cover
    discord = None
    commands = None

from commands import DiscordObjectManager, setup_commands
from database import JsonDatabase
from filesystem import FileSystemAwareness
from memory import MemoryStore
from services import ProviderManager
from tools import ToolRegistry, build_default_tools

LOGGER = logging.getLogger("inc0g.bot")

SYSTEM_PROMPT = """You are INC0G, a professional Discord AI operating system. You gather context, search memory and files, inspect server state when available, plan carefully, act safely, and never reveal secrets."""


class IncogRuntime:
    def __init__(self, root: str = ".") -> None:
        self.db = JsonDatabase("data.json")
        self.fs = FileSystemAwareness(root)
        self.memory = MemoryStore(self.db)
        self.providers = ProviderManager()
        self.tools: ToolRegistry = build_default_tools(self.fs, self.memory, self.providers)
        self.discord_manager = DiscordObjectManager()

    def state(self, guild: Any = None, channel: Any = None) -> dict[str, Any]:
        return {
            "provider": self.providers.current_provider.name,
            "memory_size": self.memory.size(),
            "guild": getattr(guild, "name", None),
            "channel": getattr(channel, "name", None),
            "tools": self.tools.names(),
        }

    async def answer(self, prompt: str, ctx: Any = None) -> str:
        guild = getattr(ctx, "guild", None)
        channel = getattr(ctx, "channel", None)
        author = getattr(ctx, "author", None)
        memories = self.memory.search(prompt, limit=5)
        files = self.fs.scan()
        state = self.state(guild, channel)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Request: {prompt}\n"
                    f"State: {state}\n"
                    f"Relevant memory: {memories}\n"
                    f"Project files: {files}\n"
                    f"Author: {getattr(author, 'display_name', None)}"
                ),
            },
        ]
        try:
            self.db.update_metric("commands")
            return await self.providers.complete(messages)
        except Exception as exc:  # noqa: BLE001 - user-facing bot must not crash
            LOGGER.exception("INC0G failed to answer")
            self.db.update_metric("errors")
            return f"INC0G recovered from an error and logged it: {exc}"


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

        def incog_state(self) -> dict[str, Any]:
            return self.runtime.state()

        async def answer(self, prompt: str, ctx: Any = None) -> str:
            return await self.runtime.answer(prompt, ctx=ctx)

        async def on_ready(self) -> None:
            LOGGER.info("INC0G connected as %s", self.user)
else:
    IncogBot = None  # type: ignore[assignment]
