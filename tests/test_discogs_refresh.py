"""Tests for refresh_stale_prices (Plan 2 Step 5)."""

import time

import httpx
import pytest

from vinyl_detective.db import init_db, get_release, upsert_release
from vinyl_detective.discogs import DiscogsClient, refresh_stale_prices
from vinyl_detective.rate_limiter import RateLimiter

PRICES_A = {
    "Very Good Plus (VG+)": {"currency": "USD", "value": 20.00},
    "Good (G)": {"currency": "USD", "value": 8.00},
}

PRICES_B = {
    "Very Good Plus (VG+)": {"currency": "USD", "value": 35.50},
    "Good (G)": {"currency": "USD", "value": 12.00},
}


def _seed_db(conn):
    """Insert two releases: one stale (30 days old), one fresh (1 day old)."""
    now = int(time.time())
    upsert_release(conn, release_id=100, artist="Artist A", title="Album A",
                   catalog_no="CAT-100", barcode=None, format_="Vinyl",
                   median_price=5.0, low_price=2.0)
    conn.execute(
        "UPDATE discogs_releases SET updated_at = ? WHERE release_id = ?",
        (now - 30 * 86400, 100),
    )
    upsert_release(conn, release_id=200, artist="Artist B", title="Album B",
                   catalog_no="CAT-200", barcode=None, format_="CD",
                   median_price=10.0, low_price=4.0)
    conn.execute(
        "UPDATE discogs_releases SET updated_at = ? WHERE release_id = ?",
        (now - 1 * 86400, 200),
    )
    conn.commit()


def _make_transport(prices_by_id):
    """Mock transport that returns prices keyed by release_id."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/marketplace/price_suggestions/" in path:
            rid = int(path.rstrip("/").split("/")[-1])
            if rid in prices_by_id:
                return httpx.Response(200, json=prices_by_id[rid])
            return httpx.Response(404, text="Not found")
        return httpx.Response(404, text="Not found")
    return httpx.MockTransport(handler)


def _patched_client(transport: httpx.MockTransport) -> DiscogsClient:
    client = DiscogsClient(token="tok", rate_limiter=RateLimiter(600))
    client._client = httpx.AsyncClient(
        transport=transport, base_url="https://api.discogs.com"
    )
    return client


@pytest.mark.asyncio
async def test_refresh_stale_only():
    """Only the stale release (30 days old) should be refreshed."""
    conn = init_db(":memory:")
    _seed_db(conn)

    transport = _make_transport({100: PRICES_A, 200: PRICES_B})
    async with _patched_client(transport) as c:
        count = await refresh_stale_prices(c, conn, max_age_days=7)

    assert count == 1
    stale = get_release(conn, 100)
    assert stale["median_price"] == 20.00
    assert stale["low_price"] == 8.00

    fresh = get_release(conn, 200)
    assert fresh["median_price"] == 10.0
    assert fresh["low_price"] == 4.0


@pytest.mark.asyncio
async def test_refresh_skips_when_no_prices():
    """If price endpoint returns 404, the release is skipped (not counted)."""
    conn = init_db(":memory:")
    _seed_db(conn)

    transport = _make_transport({})  # all 404
    async with _patched_client(transport) as c:
        count = await refresh_stale_prices(c, conn, max_age_days=7)

    assert count == 0
    stale = get_release(conn, 100)
    assert stale["median_price"] == 5.0  # unchanged


@pytest.mark.asyncio
async def test_refresh_continues_on_error():
    """If one release errors, the batch continues with the rest."""
    conn = init_db(":memory:")
    now = int(time.time())
    for rid, artist in [(300, "Artist C"), (400, "Artist D")]:
        upsert_release(conn, release_id=rid, artist=artist,
                       title=f"Album {artist[-1]}", catalog_no=None,
                       barcode=None, format_="Vinyl",
                       median_price=1.0, low_price=0.5)
        conn.execute(
            "UPDATE discogs_releases SET updated_at = ? WHERE release_id = ?",
            (now - 30 * 86400, rid),
        )
    conn.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        rid = int(path.rstrip("/").split("/")[-1])
        if rid == 300:
            return httpx.Response(500, text="Server Error")
        if rid == 400:
            return httpx.Response(200, json=PRICES_A)
        return httpx.Response(404, text="Not found")

    transport = httpx.MockTransport(handler)
    async with _patched_client(transport) as c:
        count = await refresh_stale_prices(c, conn, max_age_days=7)

    assert count == 1
    assert get_release(conn, 400)["median_price"] == 20.00


@pytest.mark.asyncio
async def test_refresh_all_stale_when_age_zero():
    """With max_age_days=0, all releases are considered stale."""
    conn = init_db(":memory:")
    _seed_db(conn)

    transport = _make_transport({100: PRICES_A, 200: PRICES_B})
    async with _patched_client(transport) as c:
        count = await refresh_stale_prices(c, conn, max_age_days=0)

    assert count == 2
    assert get_release(conn, 100)["median_price"] == 20.00
    assert get_release(conn, 200)["median_price"] == 35.50
