"""Entry point for the INC0G Discord AI operating system."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from bot import IncogBot, IncogRuntime

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def load_credentials(path: str = "credentials.txt") -> None:
    """Load KEY=VALUE credentials into the environment without printing secrets."""
    file_path = Path(path)
    if not file_path.exists():
        return
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    logging.basicConfig(level=os.getenv("INC0G_LOG_LEVEL", "INFO"), format=LOG_FORMAT)
    load_credentials()
    runtime = IncogRuntime(root=".")
    token = os.getenv("DISCORD_TOKEN")
    if IncogBot is None:
        raise RuntimeError("discord.py is required: pip install discord.py")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured in environment or credentials.txt")
    bot = IncogBot(runtime)
    bot.run(token)


if __name__ == "__main__":
    main()
