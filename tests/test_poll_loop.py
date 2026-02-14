"""Tests for the eBay polling loop."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from vinyl_detective.db import add_search
from vinyl_detective.pipeline import poll_ebay_loop
from vinyl_detective.scorer import Deal
from vinyl_detective.matcher import MatchResult


@dataclass(frozen=True)
class FakeConfig:
    ebay_poll_minutes: int = 0
    affiliate_campaign_id: str = ""


@pytest.fixture()
def db_conn():
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
            notified INTEGER DEFAULT 0,
            first_seen INTEGER
        );
        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            min_deal_score REAL DEFAULT 0.25,
            poll_minutes INTEGER DEFAULT 30,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            deal_score REAL,
            alerted_at INTEGER
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


def _make_deal(item_id="v|001", deal_score=0.50):
    return Deal(
        item_id=item_id,
        ebay_title="Miles Davis - Kind Of Blue",
        ebay_price=15.0,
        shipping=4.0,
        condition="Used",
        seller_rating=99.5,
        match=MatchResult(
            release_id=100,
            artist="Miles Davis",
            title="Kind Of Blue",
            median_price=50.0,
            method="fuzzy",
            score=0.92,
        ),
        deal_score=deal_score,
        priority="high",
        item_web_url="https://www.ebay.com/itm/001",
    )


# ---- Test 1: one active search, loop runs scan_and_score + send_deal_alerts ----

@pytest.mark.asyncio
async def test_poll_loop_calls_scan_and_alerts(db_conn):
    """Loop fetches active searches, scans, filters, and sends alerts."""
    add_search(db_conn, chat_id=42, query="vinyl records", min_deal_score=0.25)
    deal = _make_deal(deal_score=0.50)
    config = FakeConfig(ebay_poll_minutes=0)
    ebay = AsyncMock()
    bot = AsyncMock()

    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise asyncio.CancelledError

    with patch("vinyl_detective.pipeline.scan_and_score", new_callable=AsyncMock, return_value=[deal]) as mock_scan, \
         patch("vinyl_detective.telegram_bot.send_deal_alerts", new_callable=AsyncMock) as mock_alerts, \
         patch("vinyl_detective.pipeline.asyncio.sleep", side_effect=fake_sleep):

        with pytest.raises(asyncio.CancelledError):
            await poll_ebay_loop(ebay, db_conn, bot, config)

        mock_scan.assert_called_once_with(ebay, db_conn, "vinyl records")
        mock_alerts.assert_called_once()
        sent_deals = mock_alerts.call_args[0][2]
        assert len(sent_deals) == 1
        assert sent_deals[0].deal_score == 0.50


# ---- Test 2: deal below threshold is filtered out ----

@pytest.mark.asyncio
async def test_poll_loop_filters_by_threshold(db_conn):
    """Deals below the search's min_deal_score are not sent."""
    add_search(db_conn, chat_id=42, query="jazz vinyl", min_deal_score=0.60)
    low_deal = _make_deal(deal_score=0.30)
    config = FakeConfig(ebay_poll_minutes=0)
    ebay = AsyncMock()
    bot = AsyncMock()

    async def cancel_after_one(_):
        raise asyncio.CancelledError

    with patch("vinyl_detective.pipeline.scan_and_score", new_callable=AsyncMock, return_value=[low_deal]), \
         patch("vinyl_detective.telegram_bot.send_deal_alerts", new_callable=AsyncMock) as mock_alerts, \
         patch("vinyl_detective.pipeline.asyncio.sleep", side_effect=cancel_after_one):

        with pytest.raises(asyncio.CancelledError):
            await poll_ebay_loop(ebay, db_conn, bot, config)

        mock_alerts.assert_not_called()


# ---- Test 3: multiple searches, each scanned ----

@pytest.mark.asyncio
async def test_poll_loop_scans_all_active_searches(db_conn):
    """Each active search triggers its own scan_and_score call."""
    add_search(db_conn, chat_id=1, query="blue note vinyl")
    add_search(db_conn, chat_id=2, query="prestige jazz")
    config = FakeConfig(ebay_poll_minutes=0)
    ebay = AsyncMock()
    bot = AsyncMock()

    async def cancel_after_one(_):
        raise asyncio.CancelledError

    with patch("vinyl_detective.pipeline.scan_and_score", new_callable=AsyncMock, return_value=[]) as mock_scan, \
         patch("vinyl_detective.pipeline.asyncio.sleep", side_effect=cancel_after_one):

        with pytest.raises(asyncio.CancelledError):
            await poll_ebay_loop(ebay, db_conn, bot, config)

        assert mock_scan.call_count == 2
        queries = [call.args[2] for call in mock_scan.call_args_list]
        assert "blue note vinyl" in queries
        assert "prestige jazz" in queries


# ---- Test 4: exception in scan_and_score doesn't crash the loop ----

@pytest.mark.asyncio
async def test_poll_loop_resilient_to_errors(db_conn):
    """An exception in scan_and_score is caught; loop continues to next iteration."""
    add_search(db_conn, chat_id=42, query="vinyl records")
    config = FakeConfig(ebay_poll_minutes=0)
    ebay = AsyncMock()
    bot = AsyncMock()

    iteration = 0

    async def fake_sleep(_):
        nonlocal iteration
        iteration += 1
        if iteration >= 2:
            raise asyncio.CancelledError

    with patch("vinyl_detective.pipeline.scan_and_score", new_callable=AsyncMock, side_effect=[RuntimeError("API down"), []]) as mock_scan, \
         patch("vinyl_detective.pipeline.asyncio.sleep", side_effect=fake_sleep):

        with pytest.raises(asyncio.CancelledError):
            await poll_ebay_loop(ebay, db_conn, bot, config)

        assert mock_scan.call_count == 2
