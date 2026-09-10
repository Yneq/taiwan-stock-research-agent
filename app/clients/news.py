from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx
from app.progress import measured, stage


class NewsSearchError(RuntimeError):
    """A normalized public-news search error safe to expose to the model."""


class NewsSearchClient:
    def __init__(
        self,
        timeout_seconds: float = 15,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "TaiwanStockResearchAgent/0.1"},
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @measured("新聞來源查詢")
    async def search(
        self,
        query: str,
        *,
        days: int = 7,
        max_results: int = 5,
        fallback_query: str | None = None,
    ) -> dict[str, Any]:
        result = await self._search_once(query, days=days, max_results=max_results)
        result['attemptedQueries'] = [query.strip()]
        result['broadened'] = False
        fallback = (fallback_query or '').strip()
        if not result['articles'] and fallback and fallback != query.strip():
            async with stage('新聞零結果：放寬關鍵字補查'):
                result = await self._search_once(fallback, days=days, max_results=max_results)
            result['attemptedQueries'] = [query.strip(), fallback]
            result['broadened'] = True
        result['searchStatus'] = 'found' if result['articles'] else 'no_matches'
        result['limitation'] = ('放寬為一般公司新聞，未必符合原主題。' if result['broadened'] else '')
        if not result['articles']:
            result['limitation'] = '本次搜尋未找到符合條件的新聞；不代表期間內沒有新聞。'
        return result

    async def _search_once(
        self, query: str, *, days: int, max_results: int,
    ) -> dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise NewsSearchError("News search query is required")
        if days < 1 or days > 30:
            raise NewsSearchError("News search days must be between 1 and 30")
        if max_results < 1 or max_results > 10:
            raise NewsSearchError("News search max_results must be between 1 and 10")

        try:
            response = await self._client.get(
                "https://news.google.com/rss/search",
                params={
                    "q": f"{normalized_query} when:{days}d",
                    "hl": "zh-TW",
                    "gl": "TW",
                    "ceid": "TW:zh-Hant",
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise NewsSearchError("Public news search timed out") from exc
        except httpx.HTTPError as exc:
            raise NewsSearchError("Public news search is unavailable") from exc

        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise NewsSearchError("Public news search returned invalid XML") from exc

        articles: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            if not title or not url or url in seen_urls:
                continue

            source_node = item.find("source")
            source = (
                (source_node.text or "").strip()
                if source_node is not None
                else ""
            )
            published_at = self._normalize_published_at(
                (item.findtext("pubDate") or "").strip()
            )
            articles.append(
                {
                    "title": title,
                    "url": url,
                    "source": source,
                    "publishedAt": published_at,
                }
            )
            seen_urls.add(url)
            if len(articles) >= max_results:
                break

        return {
            "query": normalized_query,
            "days": days,
            "articles": articles,
            "source": "Google News RSS",
        }

    @staticmethod
    def _normalize_published_at(value: str) -> str:
        if not value:
            return ""
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
