"""Web search support with citation-ready results."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> list[SearchResult]:
        params = urlencode({"q": query, "format": "json", "no_redirect": "1", "no_html": "1"})
        request = Request(f"https://api.duckduckgo.com/?{params}", headers={"User-Agent": "INC0G Discord AI Agent"})
        with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed search endpoint
            payload = json.loads(response.read().decode("utf-8"))
        results: list[SearchResult] = []
        abstract_url = payload.get("AbstractURL")
        if abstract_url:
            results.append(SearchResult(payload.get("Heading") or query, abstract_url, payload.get("AbstractText") or "No snippet provided."))
        for topic in payload.get("RelatedTopics", []):
            nested = topic.get("Topics", []) if "Topics" in topic else [topic]
            for item in nested:
                first_url = item.get("FirstURL")
                if first_url:
                    results.append(SearchResult(item.get("Text", query).split(" - ")[0][:120], first_url, item.get("Text", "")))
                if len(results) >= limit:
                    return results[:limit]
        return results[:limit]

    @staticmethod
    def format_results(results: list[SearchResult]) -> str:
        if not results:
            return "No web results found."
        return "\n".join(f"[{idx}] {result.title}\nURL: {result.url}\nSnippet: {result.snippet}" for idx, result in enumerate(results, 1))
