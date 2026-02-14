import httpx
import pytest

from vinyl_detective.discogs import DiscogsAPIError, DiscogsClient
from vinyl_detective.rate_limiter import RateLimiter

SAMPLE_SEARCH_RESULTS = {
    "results": [
        {
            "id": 1234,
            "title": "Miles Davis - Kind Of Blue",
            "format": ["Vinyl", "LP", "Album"],
            "catno": "CS 8163",
        },
        {
            "id": 5678,
            "title": "John Coltrane - A Love Supreme",
            "format": ["Vinyl", "LP"],
            "catno": "AS-77",
        },
        {
            "id": 9012,
            "title": "Art Blakey - Moanin'",
            "format": ["CD", "Album"],
            "catno": "BLP 4003",
        },
    ],
}


def _make_transport(status: int, json_body: dict | None = None, text: str = ""):
    def handler(request: httpx.Request) -> httpx.Response:
        if json_body is not None:
            return httpx.Response(status, json=json_body)
        return httpx.Response(status, text=text)
    return httpx.MockTransport(handler)


def _patched_client(transport: httpx.MockTransport) -> DiscogsClient:
    client = DiscogsClient(token="tok", rate_limiter=RateLimiter(600))
    client._client = httpx.AsyncClient(
        transport=transport, base_url="https://api.discogs.com"
    )
    return client


@pytest.mark.asyncio
async def test_search_releases_200():
    transport = _make_transport(200, json_body=SAMPLE_SEARCH_RESULTS)
    async with _patched_client(transport) as c:
        results = await c.search_releases("blue note jazz")
    assert len(results) == 3
    assert results[0] == {
        "release_id": 1234,
        "title": "Miles Davis - Kind Of Blue",
        "format": ["Vinyl", "LP", "Album"],
        "catalog_no": "CS 8163",
    }
    assert results[1]["release_id"] == 5678
    assert results[2]["catalog_no"] == "BLP 4003"


@pytest.mark.asyncio
async def test_search_releases_empty():
    transport = _make_transport(200, json_body={"results": []})
    async with _patched_client(transport) as c:
        results = await c.search_releases("nonexistent xyz")
    assert results == []


@pytest.mark.asyncio
async def test_search_releases_with_format():
    """Verify format_ param is passed through (transport captures any request)."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert "format=Vinyl" in str(request.url)
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    async with _patched_client(transport) as c:
        results = await c.search_releases("jazz", format_="Vinyl")
    assert results == []


@pytest.mark.asyncio
async def test_search_releases_500_raises():
    transport = _make_transport(500, text="Internal Server Error")
    async with _patched_client(transport) as c:
        with pytest.raises(DiscogsAPIError) as exc_info:
            await c.search_releases("jazz")
    assert exc_info.value.status_code == 500
