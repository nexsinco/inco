"""Discord command and object-management layer."""
from __future__ import annotations

import logging
from typing import Any

try:
    import discord
    from discord.ext import commands
except ImportError:  # pragma: no cover
    discord = None
    commands = None

from permissions import has_permissions

LOGGER = logging.getLogger("inc0g.commands")


class DiscordObjectManager:
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

    async def create_announcement(self, channel: Any, content: str) -> Any:
        return await channel.send(f"📢 **Announcement**\n{content}")

    async def create_webhook(self, channel: Any, name: str, actor: Any) -> Any:
        report = has_permissions(actor, ["manage_webhooks"])
        if not report.allowed:
            raise PermissionError(f"Missing permissions: {', '.join(report.missing)}")
        return await channel.create_webhook(name=name)


def setup_commands(bot: Any) -> None:
    if commands is None:
        LOGGER.warning("discord.py is not installed; command registration skipped")
        return

    @bot.command(name="incog_status")
    async def incog_status(ctx: Any) -> None:
        state = bot.incog_state(ctx)
        await ctx.reply(
            "INC0G online\n"
            f"Provider: {state['provider']}\n"
            f"Memory items: {state['memory_size']}\n"
            f"Loaded tools: {', '.join(state['tools'])}"
        )

    @bot.command(name="incog")
    async def incog(ctx: Any, *, prompt: str) -> None:
        async with ctx.typing():
            response = await bot.answer(prompt, ctx=ctx)
        await ctx.reply(response[:1900])

    @bot.command(name="remember")
    async def remember(ctx: Any, *, fact: str) -> None:
        item = bot.runtime.memory.remember("users", fact, key=str(ctx.author.id), owner_id=str(ctx.author.id), kind="preference")
        await ctx.reply(f"Remembered. Memory ID: `{item.id}`")

    @bot.command(name="forget")
    async def forget(ctx: Any, *, query: str) -> None:
        removed = bot.runtime.memory.forget(query, scope="users", key=str(ctx.author.id))
        await ctx.reply(f"Forgot {removed} matching memory item(s).")

    @bot.command(name="searchmem")
    async def searchmem(ctx: Any, *, query: str) -> None:
        memories = bot.runtime.memory.search(query, scope="users", key=str(ctx.author.id), limit=5)
        lines = [f"- `{item.get('id')}` {item.get('text')}" for item in memories]
        await ctx.reply("\n".join(lines) if lines else "No matching memories found.")
