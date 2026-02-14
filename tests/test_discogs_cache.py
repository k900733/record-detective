"""Tests for fetch_and_cache_release (Plan 2 Step 4)."""

import httpx
import pytest

from vinyl_detective.db import init_db, get_release
from vinyl_detective.discogs import DiscogsClient, fetch_and_cache_release
from vinyl_detective.rate_limiter import RateLimiter

SAMPLE_RELEASE = {
    "id": 249504,
    "title": "Nevermind",
    "artists": [{"name": "Nirvana", "id": 125246}],
    "labels": [{"name": "DGC", "catno": "DGC-24425"}],
    "formats": [{"name": "Vinyl", "qty": "1"}],
    "identifiers": [
        {"type": "Barcode", "value": "7 20642-44252-4"},
    ],
}

SAMPLE_PRICES = {
    "Very Good Plus (VG+)": {"currency": "USD", "value": 6.29},
    "Good (G)": {"currency": "USD", "value": 1.45},
}


def _make_transport(release_json=None, release_status=200,
                    price_json=None, price_status=200):
    """Mock transport that routes by URL path."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/marketplace/price_suggestions/" in path:
            if price_json is not None:
                return httpx.Response(price_status, json=price_json)
            return httpx.Response(price_status, text="")
        if "/releases/" in path:
            if release_json is not None:
                return httpx.Response(release_status, json=release_json)
            return httpx.Response(release_status, text="")
        return httpx.Response(404, text="Not found")
    return httpx.MockTransport(handler)


def _patched_client(transport: httpx.MockTransport) -> DiscogsClient:
    client = DiscogsClient(token="tok", rate_limiter=RateLimiter(600))
    client._client = httpx.AsyncClient(
        transport=transport, base_url="https://api.discogs.com"
    )
    return client


@pytest.mark.asyncio
async def test_fetch_and_cache_success():
    transport = _make_transport(
        release_json=SAMPLE_RELEASE, release_status=200,
        price_json=SAMPLE_PRICES, price_status=200,
    )
    conn = init_db(":memory:")
    async with _patched_client(transport) as c:
        result = await fetch_and_cache_release(c, conn, 249504)

    assert result is True
    row = get_release(conn, 249504)
    assert row is not None
    assert row["artist"] == "Nirvana"
    assert row["title"] == "Nevermind"
    assert row["catalog_no"] == "DGC-24425"
    assert row["barcode"] == "7 20642-44252-4"
    assert row["format"] == "Vinyl"
    assert row["median_price"] == 6.29
    assert row["low_price"] == 1.45


@pytest.mark.asyncio
async def test_fetch_and_cache_release_not_found():
    transport = _make_transport(release_status=404)
    conn = init_db(":memory:")
    async with _patched_client(transport) as c:
        result = await fetch_and_cache_release(c, conn, 999999)

    assert result is False
    assert get_release(conn, 999999) is None


@pytest.mark.asyncio
async def test_fetch_and_cache_no_prices():
    transport = _make_transport(
        release_json=SAMPLE_RELEASE, release_status=200,
        price_status=404,
    )
    conn = init_db(":memory:")
    async with _patched_client(transport) as c:
        result = await fetch_and_cache_release(c, conn, 249504)

    assert result is True
    row = get_release(conn, 249504)
    assert row is not None
    assert row["artist"] == "Nirvana"
    assert row["median_price"] is None
    assert row["low_price"] is None
