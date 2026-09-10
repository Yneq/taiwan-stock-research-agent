from __future__ import annotations

import httpx
import pytest

from app.clients.news import NewsSearchClient, NewsSearchError


RSS_PAYLOAD = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>台積電公布最新消息</title>
      <link>https://news.google.com/rss/articles/example-one</link>
      <pubDate>Wed, 05 Aug 2026 08:00:00 GMT</pubDate>
      <source url="https://example.com">範例新聞</source>
    </item>
    <item>
      <title>台積電供應鏈動態</title>
      <link>https://news.google.com/rss/articles/example-two</link>
      <pubDate>Tue, 04 Aug 2026 08:00:00 GMT</pubDate>
      <source url="https://example.org">另一媒體</source>
    </item>
  </channel>
</rss>
""".encode()


@pytest.mark.asyncio
async def test_parses_google_news_rss_results() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["hl"] == "zh-TW"
        assert "when:7d" in request.url.params["q"]
        return httpx.Response(200, content=RSS_PAYLOAD)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http_client:
        client = NewsSearchClient(client=http_client)
        result = await client.search("台積電", days=7, max_results=1)

    assert result["source"] == "Google News RSS"
    assert len(result["articles"]) == 1
    assert result["articles"][0]["source"] == "範例新聞"
    assert result["articles"][0]["publishedAt"].endswith("+00:00")


@pytest.mark.asyncio
async def test_rejects_invalid_news_search_window() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    ) as http_client:
        client = NewsSearchClient(client=http_client)
        with pytest.raises(NewsSearchError, match="between 1 and 30"):
            await client.search("台積電", days=31)


@pytest.mark.asyncio
@pytest.mark.parametrize('first_empty', [True, False])
async def test_broaden_only_on_empty_and_keep_time_window(first_empty):
    queries = []
    def handler(request):
        queries.append(request.url.params['q'])
        empty = first_empty and len(queries) == 1
        return httpx.Response(200, content=b'<rss><channel/></rss>' if empty else RSS_PAYLOAD)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await NewsSearchClient(client=http).search('台積電 AI', fallback_query='台積電')
    assert queries == (['台積電 AI when:7d', '台積電 when:7d'] if first_empty else ['台積電 AI when:7d'])
    assert result['broadened'] == first_empty
    assert result['articles']


@pytest.mark.asyncio
async def test_empty_does_not_claim_no_news_exists():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'<rss><channel/></rss>'))) as http:
        result = await NewsSearchClient(client=http).search('台積電 AI', fallback_query='台積電')
    assert result['searchStatus'] == 'no_matches'
    assert len(result['attemptedQueries']) == 2
    assert '不代表期間內沒有新聞' in result['limitation']
