"""Discord command and object-management layer."""
from __future__ import annotations

import logging
from typing import Any

try:
    import discord
    from discord.ext import commands
except ImportError:  # pragma: no cover - keeps static checks usable without discord.py installed
    discord = None
    commands = None

from permissions import has_permissions

LOGGER = logging.getLogger("inc0g.commands")


class DiscordObjectManager:
    """High-level wrapper for guild, role, channel, thread, webhook and message actions."""

    async def create_text_channel(self, guild: Any, name: str, actor: Any, **kwargs: Any) -> Any:
        report = has_permissions(actor, ["manage_channels"])
        if not report.allowed:
            raise PermissionError(f"Missing permissions: {', '.join(report.missing)}")
        return await guild.create_text_channel(name, **kwargs)

    async def create_role(self, guild: Any, name: str, actor: Any, **kwargs: Any) -> Any:
        report = has_permissions(actor, ["manage_roles"])
        if not report.allowed:
            raise PermissionError(f"Missing permissions: {', '.join(report.missing)}")
        return await guild.create_role(name=name, **kwargs)

    async def create_thread(self, channel: Any, name: str, **kwargs: Any) -> Any:
        return await channel.create_thread(name=name, **kwargs)

    async def post_message(self, channel: Any, content: str, **kwargs: Any) -> Any:
        return await channel.send(content, **kwargs)

    async def create_webhook(self, channel: Any, name: str, actor: Any) -> Any:
        report = has_permissions(actor, ["manage_webhooks"])
        if not report.allowed:
            raise PermissionError(f"Missing permissions: {', '.join(report.missing)}")
        return await channel.create_webhook(name=name)


def setup_commands(bot: Any) -> None:
    """Register slash/prefix commands when discord.py is installed."""
    if commands is None:
        LOGGER.warning("discord.py is not installed; command registration skipped")
        return

    @bot.command(name="incog_status")
    async def incog_status(ctx: Any) -> None:
        state = bot.incog_state()
        await ctx.reply(
            "INC0G online\n"
            f"Provider: {state['provider']}\n"
            f"Memory items: {state['memory_size']}\n"
            f"Tools: {', '.join(state['tools'])}"
        )

    @bot.command(name="incog")
    async def incog(ctx: Any, *, prompt: str) -> None:
        await ctx.typing()
        response = await bot.answer(prompt, ctx=ctx)
        await ctx.reply(response[:1900])
