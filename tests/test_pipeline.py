"""Tests for the scan-match-score pipeline."""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from vinyl_detective.matcher import MatchResult
from vinyl_detective.pipeline import scan_and_score
from vinyl_detective.db import init_db


def _make_listing(item_id="v|111", title="Miles Davis - Kind Of Blue LP", price=15.0):
    return {
        "item_id": item_id,
        "title": title,
        "price": price,
        "currency": "USD",
        "condition": "Used",
        "seller_rating": 99.5,
        "image_url": "https://img.example.com/1.jpg",
        "item_web_url": "https://www.ebay.com/itm/111",
        "shipping": 4.0,
    }


def _make_match(release_id=12345, median_price=50.0, method="fuzzy", score=0.92):
    return MatchResult(
        release_id=release_id,
        artist="Miles Davis",
        title="Kind Of Blue",
        median_price=median_price,
        method=method,
        score=score,
    )


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    init_db.__wrapped__(conn) if hasattr(init_db, "__wrapped__") else init_db(conn)
    yield conn
    conn.close()


@pytest.fixture()
def db_conn():
    """Standalone in-memory DB for pipeline tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS discogs_releases (
            release_id INTEGER PRIMARY KEY,
            artist TEXT NOT NULL,
            title TEXT NOT NULL,
            catalog_no TEXT,
            catalog_no_normalized TEXT,
            barcode TEXT,
            format TEXT,
            median_price REAL,
            low_price REAL,
            updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS ebay_listings (
            item_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            shipping REAL DEFAULT 0,
            condition TEXT,
            seller_rating REAL,
            match_release_id INTEGER,
            match_method TEXT,
            match_score REAL,
            deal_score REAL,
            first_seen INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS releases_fts USING fts5(
            artist, title, catalog_no,
            content='discogs_releases',
            content_rowid='release_id'
        );
        """
    )
    yield conn
    conn.close()


# ---- Test 1: 3 listings, 2 match, 1 is a deal ----

@pytest.mark.asyncio
async def test_scan_3_listings_1_deal(db_conn):
    """3 eBay listings: 2 match, only 1 scores as a deal."""
    listings = [
        _make_listing("v|001", "Miles Davis - Kind Of Blue LP", 15.0),
        _make_listing("v|002", "John Coltrane - A Love Supreme", 20.0),
        _make_listing("v|003", "Random Junk No Match", 5.0),
    ]
    match_miles = _make_match(release_id=100, median_price=50.0)
    match_coltrane = _make_match(release_id=200, median_price=22.0)

    def fake_match(conn, title, upc=None):
        if "Miles" in title:
            return match_miles
        if "Coltrane" in title:
            return match_coltrane
        return None

    ebay = AsyncMock()
    ebay.search_listings = AsyncMock(return_value=listings)
    ebay.get_item = AsyncMock(return_value=None)

    with patch("vinyl_detective.pipeline.match_listing", side_effect=fake_match), \
         patch("vinyl_detective.pipeline.score_deal", wraps=score_deal_selective(match_miles)):

        deals = await scan_and_score(ebay, db_conn, "vinyl records")

    # Coltrane total = 20+4 = 24 > median 22 -> overpriced -> None
    # Miles total = 15+4 = 19, median 50 -> deal_score ~0.62 -> deal
    assert len(deals) == 1
    assert deals[0].item_id == "v|001"


def score_deal_selective(expected_match):
    """Wrapper that uses real score_deal logic."""
    from vinyl_detective.scorer import score_deal as real_score
    def _wrap(listing, match):
        return real_score(listing, match)
    return _wrap


# ---- Test 2: empty search results ----

@pytest.mark.asyncio
async def test_scan_empty_results(db_conn):
    ebay = AsyncMock()
    ebay.search_listings = AsyncMock(return_value=[])

    deals = await scan_and_score(ebay, db_conn, "nothing here")
    assert deals == []
    ebay.get_item.assert_not_called()


# ---- Test 3: all 3 match and score -> 3 deals in DB ----

@pytest.mark.asyncio
async def test_scan_all_match_and_stored_in_db(db_conn):
    """All listings match and score; verify DB persistence."""
    listings = [
        _make_listing(f"v|{i:03d}", f"Artist{i} - Title{i}", 10.0)
        for i in range(3)
    ]
    match = _make_match(median_price=40.0)

    ebay = AsyncMock()
    ebay.search_listings = AsyncMock(return_value=listings)
    ebay.get_item = AsyncMock(return_value=None)

    with patch("vinyl_detective.pipeline.match_listing", return_value=match):
        deals = await scan_and_score(ebay, db_conn, "cheap vinyl")

    assert len(deals) == 3
    rows = db_conn.execute("SELECT item_id, deal_score FROM ebay_listings ORDER BY item_id").fetchall()
    assert len(rows) == 3
    for row in rows:
        assert row["deal_score"] is not None
        assert row["deal_score"] > 0


# ---- Test 4: catalog number skips get_item call ----

@pytest.mark.asyncio
async def test_catalog_no_skips_get_item(db_conn):
    """When title contains a catalog number, get_item is NOT called."""
    listing = _make_listing("v|cat", "BLP-4003 Lee Morgan - Sidewinder", 12.0)
    match = _make_match(median_price=80.0, method="catalog_no", score=1.0)

    ebay = AsyncMock()
    ebay.search_listings = AsyncMock(return_value=[listing])
    ebay.get_item = AsyncMock()

    with patch("vinyl_detective.pipeline.match_listing", return_value=match):
        deals = await scan_and_score(ebay, db_conn, "blue note")

    assert len(deals) == 1
    ebay.get_item.assert_not_called()
