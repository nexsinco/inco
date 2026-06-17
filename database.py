"""Persistent JSON database primitives for INC0G."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any, Callable

LOGGER = logging.getLogger("inc0g.database")


class JsonDatabase:
    """Small durable JSON store with defensive reads and atomic writes."""

    def __init__(self, path: str | Path = "data.json") -> None:
        self.path = Path(path)
        self._lock = RLock()
        self.data: dict[str, Any] = self._load()

    def _default(self) -> dict[str, Any]:
        return {
            "memory": {"users": {}, "guilds": {}, "channels": {}, "tasks": {}, "global": []},
            "config": {"personality": "INC0G", "provider_rotation": ["groq", "openrouter", "together"]},
            "metrics": {"commands": 0, "errors": 0, "tool_usage": {}, "providers": {}},
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default()
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                base = self._default()
                base.update(loaded)
                return base
        except json.JSONDecodeError:
            LOGGER.exception("data.json is invalid; starting with safe defaults")
        return self._default()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, *keys: str, default: Any = None) -> Any:
        cursor: Any = self.data
        for key in keys:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    def set(self, keys: list[str], value: Any) -> None:
        with self._lock:
            cursor = self.data
            for key in keys[:-1]:
                cursor = cursor.setdefault(key, {})
            cursor[keys[-1]] = value
            self.save()

    def update_metric(self, key: str, amount: int = 1) -> None:
        with self._lock:
            metrics = self.data.setdefault("metrics", {})
            metrics[key] = int(metrics.get(key, 0)) + amount
            self.save()

    def mutate(self, mutator: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            mutator(self.data)
            self.save()
