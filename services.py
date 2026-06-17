"""Real async AI provider integrations for INC0G."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("inc0g.providers")


@dataclass(slots=True)
class ProviderStats:
    healthy: bool = False
    failures: int = 0
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    last_error: str | None = None
    latency_ms: float = 0.0


@dataclass(slots=True)
class AIProvider:
    name: str
    api_key_env: str
    base_url: str
    default_model: str
    model_env: str
    timeout: float = 45.0
    input_cost_per_1k_tokens: float = 0.0
    output_cost_per_1k_tokens: float = 0.0
    stats: ProviderStats = field(default_factory=ProviderStats)

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env)

    @property
    def model(self) -> str:
        return os.getenv(self.model_env, self.default_model)

    def configured(self) -> bool:
        return bool(self.api_key)

    async def health_check(self) -> bool:
        if not self.configured():
            self.stats.healthy = False
            self.stats.last_error = f"{self.api_key_env} is not configured"
            return False
        try:
            await self.complete([{"role": "user", "content": "Reply with OK."}], max_tokens=4, temperature=0)
            self.stats.healthy = True
            return True
        except Exception as exc:  # noqa: BLE001
            self.stats.healthy = False
            self.stats.last_error = str(exc)
            return False

    async def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.3, max_tokens: int = 1400) -> str:
        return await asyncio.to_thread(self._complete_sync, messages, temperature, max_tokens)

    def _complete_sync(self, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
        if not self.api_key:
            raise RuntimeError(f"{self.name} is not configured; set {self.api_key_env}")
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "INC0G Discord AI Agent"}
        if self.name == "openrouter":
            headers.update({"HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://github.com/nexsinco/inco"), "X-Title": "INC0G"})
        request = Request(f"{self.base_url.rstrip('/')}/chat/completions", data=payload, headers=headers, method="POST")
        started = monotonic()
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - provider URLs are fixed constants
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.name} returned HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.name} request failed: {exc.reason}") from exc
        self.stats.latency_ms = (monotonic() - started) * 1000
        try:
            content = body["choices"][0]["message"].get("content", "")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{self.name} returned an invalid chat completion payload") from exc
        if not content:
            raise RuntimeError(f"{self.name} returned an empty response")
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens", estimate_tokens(messages)))
        completion_tokens = int(usage.get("completion_tokens", estimate_tokens([{"content": content}])))
        self.stats.requests += 1
        self.stats.input_tokens += prompt_tokens
        self.stats.output_tokens += completion_tokens
        self.stats.total_tokens += prompt_tokens + completion_tokens
        self.stats.estimated_cost_usd += (prompt_tokens / 1000 * self.input_cost_per_1k_tokens) + (completion_tokens / 1000 * self.output_cost_per_1k_tokens)
        self.stats.healthy = True
        self.stats.last_error = None
        return str(content).strip()


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    words = sum(len(str(message.get("content", "")).split()) for message in messages)
    return max(1, int(words * 1.35))


class ProviderManager:
    def __init__(self, providers: list[AIProvider] | None = None, retries: int = 2) -> None:
        self.providers = providers or [
            AIProvider("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_MODEL", input_cost_per_1k_tokens=0.00059, output_cost_per_1k_tokens=0.00079),
            AIProvider("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini", "OPENROUTER_MODEL", input_cost_per_1k_tokens=0.00015, output_cost_per_1k_tokens=0.0006),
            AIProvider("together", "TOGETHER_API_KEY", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_MODEL", input_cost_per_1k_tokens=0.00088, output_cost_per_1k_tokens=0.00088),
        ]
        self.retries = retries
        self._cursor = 0

    @property
    def current_provider(self) -> AIProvider:
        return self.providers[self._cursor % len(self.providers)]

    async def health_checks(self) -> dict[str, bool]:
        results = await asyncio.gather(*(provider.health_check() for provider in self.providers), return_exceptions=True)
        return {provider.name: bool(result) for provider, result in zip(self.providers, results)}

    async def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.3, max_tokens: int = 1400) -> str:
        if not any(provider.configured() for provider in self.providers):
            raise RuntimeError("No AI providers are configured. Set GROQ_API_KEY, OPENROUTER_API_KEY, or TOGETHER_API_KEY.")
        errors: list[str] = []
        for _ in range(len(self.providers)):
            provider = self.current_provider
            self._cursor += 1
            if not provider.configured():
                continue
            for attempt in range(self.retries + 1):
                try:
                    return await provider.complete(messages, temperature=temperature, max_tokens=max_tokens)
                except Exception as exc:  # noqa: BLE001
                    provider.stats.failures += 1
                    provider.stats.healthy = False
                    provider.stats.last_error = str(exc)
                    errors.append(f"{provider.name} attempt {attempt + 1}: {exc}")
                    LOGGER.warning("Provider failure: %s", errors[-1])
                    await asyncio.sleep(min(2.0, 0.4 * (attempt + 1)))
        raise RuntimeError("All configured AI providers failed: " + "; ".join(errors))

    def usage_report(self) -> dict[str, dict[str, Any]]:
        return {provider.name: {"model": provider.model, **asdict(provider.stats)} for provider in self.providers}
