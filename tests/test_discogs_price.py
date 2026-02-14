import httpx
import pytest

from vinyl_detective.discogs import DiscogsAPIError, DiscogsClient
from vinyl_detective.rate_limiter import RateLimiter

SAMPLE_PRICES = {
    "Mint (M)": {"currency": "USD", "value": 9.19},
    "Near Mint (NM or M-)": {"currency": "USD", "value": 8.22},
    "Very Good Plus (VG+)": {"currency": "USD", "value": 6.29},
    "Very Good (VG)": {"currency": "USD", "value": 4.35},
    "Good Plus (G+)": {"currency": "USD", "value": 2.42},
    "Good (G)": {"currency": "USD", "value": 1.45},
    "Fair (F)": {"currency": "USD", "value": 0.97},
    "Poor (P)": {"currency": "USD", "value": 0.48},
}

SAMPLE_PRICES_NO_VGP = {
    "Mint (M)": {"currency": "USD", "value": 9.19},
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
async def test_get_price_stats_200():
    transport = _make_transport(200, json_body=SAMPLE_PRICES)
    async with _patched_client(transport) as c:
        result = await c.get_price_stats(249504)
    assert result is not None
    assert result["median_price"] == 6.29
    assert result["low_price"] == 1.45


@pytest.mark.asyncio
async def test_get_price_stats_no_vgp():
    transport = _make_transport(200, json_body=SAMPLE_PRICES_NO_VGP)
    async with _patched_client(transport) as c:
        result = await c.get_price_stats(249504)
    assert result is None


@pytest.mark.asyncio
async def test_get_price_stats_404():
    transport = _make_transport(404, text="Not found")
    async with _patched_client(transport) as c:
        result = await c.get_price_stats(999999)
    assert result is None


@pytest.mark.asyncio
async def test_get_price_stats_500_raises():
    transport = _make_transport(500, text="Internal Server Error")
    async with _patched_client(transport) as c:
        with pytest.raises(DiscogsAPIError) as exc_info:
            await c.get_price_stats(249504)
    assert exc_info.value.status_code == 500
