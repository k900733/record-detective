"""End-to-end integration test: DB setup -> pipeline -> alerts -> dedup."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from vinyl_detective.db import (
    add_search,
    init_db,
    upsert_release,
    was_alerted,
)
from vinyl_detective.pipeline import scan_and_score
from vinyl_detective.telegram_bot import send_deal_alerts


# -- Fixtures --

@pytest.fixture()
def conn():
    """In-memory DB with schema + seed data (3 Discogs releases, 1 saved search)."""
    c = init_db(":memory:")

    upsert_release(c, release_id=1001, artist="Miles Davis", title="Kind Of Blue",
                   catalog_no="CS-8163", barcode="074646508817",
                   median_price=50.0, format_="Vinyl")
    upsert_release(c, release_id=1002, artist="John Coltrane", title="A Love Supreme",
                   catalog_no="AS-77", barcode="602498840184",
                   median_price=40.0, format_="Vinyl")
    upsert_release(c, release_id=1003, artist="Thelonious Monk", title="Brilliant Corners",
                   catalog_no="RLP 12-226", median_price=60.0, format_="Vinyl")

    add_search(c, chat_id=12345, query="jazz vinyl", min_deal_score=0.25)
    yield c
    c.close()


def _ebay_listings():
    """5 eBay listings: 2 underpriced deals, 1 overpriced match, 2 no match."""
    return [
        {   # -> barcode match via get_item UPC enrichment
            "item_id": "e|001",
            "title": "Miles Davis Kind Of Blue LP",
            "price": 15.0,
            "currency": "USD",
            "condition": "Very Good Plus (VG+)",
            "seller_rating": 99.1,
            "image_url": "https://img.example.com/1.jpg",
            "item_web_url": "https://www.ebay.com/itm/001",
            "shipping": 4.0,
        },
        {   # -> catalog match (AS-77 in title)
            "item_id": "e|002",
            "title": "AS-77 John Coltrane A Love Supreme Vinyl",
            "price": 18.0,
            "currency": "USD",
            "condition": "Near Mint (NM)",
            "seller_rating": 98.0,
            "image_url": "https://img.example.com/2.jpg",
            "item_web_url": "https://www.ebay.com/itm/002",
            "shipping": 3.0,
        },
        {   # -> no match (not in DB)
            "item_id": "e|003",
            "title": "Random Pop Album No Match",
            "price": 5.0,
            "currency": "USD",
            "condition": "Good (G)",
            "seller_rating": 90.0,
            "image_url": "https://img.example.com/3.jpg",
            "item_web_url": "https://www.ebay.com/itm/003",
            "shipping": 2.0,
        },
        {   # -> no match (not in DB)
            "item_id": "e|004",
            "title": "Beatles Abbey Road Vinyl",
            "price": 25.0,
            "currency": "USD",
            "condition": "Very Good (VG)",
            "seller_rating": 95.0,
            "image_url": "https://img.example.com/4.jpg",
            "item_web_url": "https://www.ebay.com/itm/004",
            "shipping": 5.0,
        },
        {   # -> fuzzy match but overpriced (55+10=65 > median 60)
            "item_id": "e|005",
            "title": "Thelonious Monk Brilliant Corners",
            "price": 55.0,
            "currency": "USD",
            "condition": "Very Good Plus (VG+)",
            "seller_rating": 97.0,
            "image_url": "https://img.example.com/5.jpg",
            "item_web_url": "https://www.ebay.com/itm/005",
            "shipping": 10.0,
        },
    ]


def _miles_item_detail():
    """Simulated get_item response with UPC in localizedAspects."""
    return {
        "item_id": "e|001",
        "title": "Miles Davis Kind Of Blue LP",
        "description": "Original pressing",
        "localized_aspects": [
            {"name": "Artist", "value": "Miles Davis"},
            {"name": "UPC", "value": "074646508817"},
        ],
        "item_location": "US",
        "price": 15.0,
        "currency": "USD",
        "condition": "Very Good Plus (VG+)",
        "item_web_url": "https://www.ebay.com/itm/001",
    }


def _make_ebay_mock():
    ebay = AsyncMock()
    ebay.search_listings = AsyncMock(return_value=_ebay_listings())

    def get_item_side_effect(item_id):
        if item_id == "e|001":
            return _miles_item_detail()
        return None

    ebay.get_item = AsyncMock(side_effect=get_item_side_effect)
    return ebay


# -- Tests --

@pytest.mark.asyncio
async def test_e2e_pipeline_finds_two_deals(conn):
    """Full pipeline: 5 listings -> 2 underpriced deals scored and persisted."""
    ebay = _make_ebay_mock()

    deals = await scan_and_score(ebay, conn, "jazz vinyl")

    assert len(deals) == 2
    deal_ids = {d.item_id for d in deals}
    assert deal_ids == {"e|001", "e|002"}

    # Miles Davis: barcode match, total=19, median=50 -> score=0.62
    miles = next(d for d in deals if d.item_id == "e|001")
    assert miles.match.release_id == 1001
    assert miles.match.method == "barcode"
    assert 0.5 < miles.deal_score < 0.7

    # Coltrane: catalog match, total=21, median=40 -> score=0.475
    coltrane = next(d for d in deals if d.item_id == "e|002")
    assert coltrane.match.release_id == 1002
    assert coltrane.match.method == "catalog_no"
    assert 0.4 < coltrane.deal_score < 0.55


@pytest.mark.asyncio
async def test_e2e_deals_persisted_in_db(conn):
    """Both deals appear in ebay_listings with correct match_release_id and deal_score."""
    ebay = _make_ebay_mock()

    await scan_and_score(ebay, conn, "jazz vinyl")

    rows = conn.execute(
        "SELECT item_id, match_release_id, match_method, deal_score "
        "FROM ebay_listings WHERE deal_score IS NOT NULL ORDER BY item_id"
    ).fetchall()
    assert len(rows) == 2

    r1 = dict(rows[0])
    assert r1["item_id"] == "e|001"
    assert r1["match_release_id"] == 1001
    assert r1["match_method"] == "barcode"
    assert r1["deal_score"] > 0

    r2 = dict(rows[1])
    assert r2["item_id"] == "e|002"
    assert r2["match_release_id"] == 1002
    assert r2["match_method"] == "catalog_no"
    assert r2["deal_score"] > 0


@pytest.mark.asyncio
async def test_e2e_alerts_sent(conn):
    """After pipeline, send_deal_alerts sends 2 messages (one per deal)."""
    ebay = _make_ebay_mock()
    deals = await scan_and_score(ebay, conn, "jazz vinyl")

    bot = AsyncMock()
    await send_deal_alerts(bot, conn, deals)

    assert bot.send_message.call_count == 2
    chat_ids = {c.kwargs["chat_id"] for c in bot.send_message.call_args_list}
    assert chat_ids == {12345}

    assert was_alerted(conn, 12345, "e|001")
    assert was_alerted(conn, 12345, "e|002")


@pytest.mark.asyncio
async def test_e2e_dedup_no_repeat_alerts(conn):
    """Run pipeline + alerts twice with identical data; second run sends 0 messages."""
    ebay = _make_ebay_mock()

    # First run
    deals1 = await scan_and_score(ebay, conn, "jazz vinyl")
    bot = AsyncMock()
    await send_deal_alerts(bot, conn, deals1)
    assert bot.send_message.call_count == 2

    # Second run (same listings)
    ebay2 = _make_ebay_mock()
    deals2 = await scan_and_score(ebay2, conn, "jazz vinyl")
    bot2 = AsyncMock()
    await send_deal_alerts(bot2, conn, deals2)

    bot2.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_e2e_alert_log_entries(conn):
    """Alert log contains correct records after pipeline + alerts."""
    ebay = _make_ebay_mock()
    deals = await scan_and_score(ebay, conn, "jazz vinyl")

    bot = AsyncMock()
    await send_deal_alerts(bot, conn, deals)

    rows = conn.execute(
        "SELECT chat_id, item_id, deal_score FROM alert_log ORDER BY item_id"
    ).fetchall()
    assert len(rows) == 2
    assert dict(rows[0])["chat_id"] == 12345
    assert dict(rows[0])["item_id"] == "e|001"
    assert dict(rows[1])["chat_id"] == 12345
    assert dict(rows[1])["item_id"] == "e|002"
