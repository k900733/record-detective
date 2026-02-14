import httpx
import pytest

from vinyl_detective.discogs import DiscogsAPIError, DiscogsClient, _parse_release
from vinyl_detective.rate_limiter import RateLimiter

SAMPLE_RELEASE = {
    "id": 249504,
    "title": "Nevermind",
    "artists": [{"name": "Nirvana", "id": 125246}],
    "labels": [{"name": "DGC", "catno": "DGC-24425"}],
    "formats": [{"name": "Vinyl", "qty": "1"}],
    "identifiers": [
        {"type": "Barcode", "value": "7 20642-44252-4"},
        {"type": "Matrix / Runout", "value": "ABC-123"},
    ],
}


def _make_transport(status: int, json_body: dict | None = None, text: str = ""):
    """Build an httpx.MockTransport returning a fixed response."""
    def handler(request: httpx.Request) -> httpx.Response:
        if json_body is not None:
            return httpx.Response(status, json=json_body)
        return httpx.Response(status, text=text)
    return httpx.MockTransport(handler)


def _patched_client(transport: httpx.MockTransport) -> DiscogsClient:
    """Create a DiscogsClient whose internal httpx client uses a mock transport."""
    client = DiscogsClient(token="tok", rate_limiter=RateLimiter(600))
    client._client = httpx.AsyncClient(
        transport=transport, base_url="https://api.discogs.com"
    )
    return client


# -- _parse_release unit tests --

def test_parse_release_full():
    result = _parse_release(SAMPLE_RELEASE)
    assert result == {
        "release_id": 249504,
        "artist": "Nirvana",
        "title": "Nevermind",
        "catalog_no": "DGC-24425",
        "barcode": "7 20642-44252-4",
        "format": "Vinyl",
    }


def test_parse_release_strips_artist_suffix():
    data = {**SAMPLE_RELEASE, "artists": [{"name": "The Beatles (2)"}]}
    assert _parse_release(data)["artist"] == "The Beatles"


def test_parse_release_missing_optional_fields():
    data = {"id": 1, "title": "X"}
    result = _parse_release(data)
    assert result["artist"] == ""
    assert result["catalog_no"] == ""
    assert result["barcode"] == ""
    assert result["format"] == ""


def test_parse_release_no_barcode_identifier():
    data = {
        **SAMPLE_RELEASE,
        "identifiers": [{"type": "Matrix / Runout", "value": "ABC"}],
    }
    assert _parse_release(data)["barcode"] == ""


# -- get_release integration tests --

@pytest.mark.asyncio
async def test_get_release_200():
    transport = _make_transport(200, json_body=SAMPLE_RELEASE)
    async with _patched_client(transport) as c:
        result = await c.get_release(249504)
    assert result is not None
    assert result["release_id"] == 249504
    assert result["artist"] == "Nirvana"
    assert result["title"] == "Nevermind"
    assert result["catalog_no"] == "DGC-24425"
    assert result["barcode"] == "7 20642-44252-4"
    assert result["format"] == "Vinyl"


@pytest.mark.asyncio
async def test_get_release_404():
    transport = _make_transport(404, text="Not found")
    async with _patched_client(transport) as c:
        result = await c.get_release(999999)
    assert result is None


@pytest.mark.asyncio
async def test_get_release_429_raises():
    transport = _make_transport(429, text="Rate limited")
    async with _patched_client(transport) as c:
        with pytest.raises(DiscogsAPIError) as exc_info:
            await c.get_release(249504)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_get_release_500_raises():
    transport = _make_transport(500, text="Internal Server Error")
    async with _patched_client(transport) as c:
        with pytest.raises(DiscogsAPIError) as exc_info:
            await c.get_release(249504)
    assert exc_info.value.status_code == 500
    assert "500" in str(exc_info.value)
