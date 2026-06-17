"""Permission helpers for safe Discord operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DANGEROUS_PERMISSIONS = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members",
    "manage_messages",
}


@dataclass(slots=True)
class PermissionReport:
    allowed: bool
    missing: list[str]
    dangerous: list[str]


def has_permissions(actor: Any, required: list[str]) -> PermissionReport:
    permissions = getattr(actor, "guild_permissions", actor)
    missing = [name for name in required if not bool(getattr(permissions, name, False))]
    dangerous = [name for name in required if name in DANGEROUS_PERMISSIONS]
    return PermissionReport(allowed=not missing, missing=missing, dangerous=dangerous)


def assert_safe_text(text: str) -> str:
    """Redact common secret-looking values before logging or displaying text."""
    redacted = text
    markers = ["token", "api_key", "apikey", "password", "secret", "authorization"]
    for marker in markers:
        redacted = redacted.replace(marker.upper(), "[REDACTED]").replace(marker, "[redacted]")
    return redacted
