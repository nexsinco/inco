"""AI provider abstraction with retries, rotation, health, token and cost tracking."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any

LOGGER = logging.getLogger("inc0g.providers")


@dataclass(slots=True)
class ProviderStats:
    healthy: bool = True
    failures: int = 0
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    last_error: str | None = None
    latency_ms: float = 0.0


@dataclass(slots=True)
class AIProvider:
    name: str
    api_key_env: str
    base_url: str
    model: str
    timeout: float = 30.0
    cost_per_1k_tokens: float = 0.0
    stats: ProviderStats = field(default_factory=ProviderStats)

    def configured(self) -> bool:
        return bool(os.getenv(self.api_key_env))

    async def health_check(self) -> bool:
        self.stats.healthy = self.configured()
        return self.stats.healthy

    async def complete(self, messages: list[dict[str, str]], **_: Any) -> str:
        if not self.configured():
            raise RuntimeError(f"{self.name} is not configured; set {self.api_key_env}")
        # Network client intentionally centralized for future expansion. Returning a deterministic
        # local response keeps the skeleton runnable without leaking provider credentials.
        await asyncio.sleep(0)
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        return f"INC0G provider {self.name} received {prompt_tokens} prompt tokens and is ready for live API integration."


class ProviderManager:
    def __init__(self, providers: list[AIProvider] | None = None, retries: int = 2) -> None:
        self.providers = providers or [
            AIProvider("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", cost_per_1k_tokens=0.0006),
            AIProvider("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini", cost_per_1k_tokens=0.001),
            AIProvider("together", "TOGETHER_API_KEY", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", cost_per_1k_tokens=0.0009),
        ]
        self.retries = retries
        self._cursor = 0

    @property
    def current_provider(self) -> AIProvider:
        return self.providers[self._cursor % len(self.providers)]

    async def health_checks(self) -> dict[str, bool]:
        return {provider.name: await provider.health_check() for provider in self.providers}

    async def complete(self, messages: list[dict[str, str]]) -> str:
        errors: list[str] = []
        for _ in range(len(self.providers)):
            provider = self.current_provider
            self._cursor += 1
            for attempt in range(self.retries + 1):
                started = monotonic()
                try:
                    result = await asyncio.wait_for(provider.complete(messages), timeout=provider.timeout)
                    tokens = sum(len(m.get("content", "").split()) for m in messages) + len(result.split())
                    provider.stats.requests += 1
                    provider.stats.input_tokens += tokens
                    provider.stats.estimated_cost_usd += tokens / 1000 * provider.cost_per_1k_tokens
                    provider.stats.latency_ms = (monotonic() - started) * 1000
                    provider.stats.healthy = True
                    return result
                except Exception as exc:  # noqa: BLE001 - providers must fail over on any client error
                    provider.stats.failures += 1
                    provider.stats.last_error = str(exc)
                    provider.stats.healthy = False
                    errors.append(f"{provider.name} attempt {attempt + 1}: {exc}")
                    LOGGER.warning("Provider failure: %s", errors[-1])
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise RuntimeError("All AI providers failed: " + "; ".join(errors))

    def usage_report(self) -> dict[str, dict[str, Any]]:
        return {provider.name: asdict(provider.stats) for provider in self.providers}
