"""Tests for send_deal_alerts function."""

from unittest.mock import AsyncMock

import pytest

from vinyl_detective import db
from vinyl_detective.matcher import MatchResult
from vinyl_detective.scorer import Deal
from vinyl_detective.telegram_bot import send_deal_alerts


@pytest.fixture()
def conn():
    c = db.init_db(":memory:")
    yield c
    c.close()


def _make_deal(item_id="item-1", score=0.6, price=20.0, web_url="https://ebay.com/itm/1"):
    match = MatchResult(
        release_id=1,
        artist="Art Blakey",
        title="Moanin'",
        median_price=50.0,
        method="catalog_no",
        score=1.0,
    )
    return Deal(
        item_id=item_id,
        ebay_title="Art Blakey Moanin LP",
        ebay_price=price,
        shipping=0.0,
        condition="Very Good Plus (VG+)",
        seller_rating=99.5,
        match=match,
        deal_score=score,
        priority="high",
        item_web_url=web_url,
    )


@pytest.mark.asyncio
async def test_send_alert_basic(conn):
    """One deal, one matching search -> send_message called once."""
    db.add_search(conn, chat_id=111, query="blue note jazz", min_deal_score=0.25)
    bot = AsyncMock()
    deal = _make_deal()

    await send_deal_alerts(bot, conn, [deal])

    bot.send_message.assert_called_once()
    call_kw = bot.send_message.call_args
    assert call_kw.kwargs["chat_id"] == 111
    assert call_kw.kwargs["parse_mode"] == "HTML"
    assert "Art Blakey" in call_kw.kwargs["text"]


@pytest.mark.asyncio
async def test_duplicate_suppressed(conn):
    """Already-alerted (chat, item) pair is not sent again."""
    db.add_search(conn, chat_id=111, query="jazz", min_deal_score=0.25)
    db.log_alert(conn, chat_id=111, item_id="item-1", deal_score=0.6)
    bot = AsyncMock()
    deal = _make_deal()

    await send_deal_alerts(bot, conn, [deal])

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_chats(conn):
    """Two searches for different chats -> send_message called twice."""
    db.add_search(conn, chat_id=111, query="jazz", min_deal_score=0.25)
    db.add_search(conn, chat_id=222, query="vinyl", min_deal_score=0.25)
    bot = AsyncMock()
    deal = _make_deal()

    await send_deal_alerts(bot, conn, [deal])

    assert bot.send_message.call_count == 2
    chat_ids = {c.kwargs["chat_id"] for c in bot.send_message.call_args_list}
    assert chat_ids == {111, 222}


@pytest.mark.asyncio
async def test_threshold_filtering(conn):
    """Search with min_deal_score above deal score -> not sent."""
    db.add_search(conn, chat_id=111, query="jazz", min_deal_score=0.80)
    bot = AsyncMock()
    deal = _make_deal(score=0.6)

    await send_deal_alerts(bot, conn, [deal])

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_affiliate_url_appended(conn):
    """When campaign_id given, affiliate params appear in the message."""
    db.add_search(conn, chat_id=111, query="jazz", min_deal_score=0.25)
    bot = AsyncMock()
    deal = _make_deal()

    await send_deal_alerts(bot, conn, [deal], affiliate_campaign_id="CAMP123")

    text = bot.send_message.call_args.kwargs["text"]
    assert "CAMP123" in text


@pytest.mark.asyncio
async def test_mark_notified_called(conn):
    """After successful send, item is marked notified in DB."""
    db.add_search(conn, chat_id=111, query="jazz", min_deal_score=0.25)
    # Insert a listing row so mark_notified has something to update
    conn.execute(
        "INSERT INTO ebay_listings (item_id, title, price) VALUES (?, ?, ?)",
        ("item-1", "Test", 20.0),
    )
    conn.commit()
    bot = AsyncMock()
    deal = _make_deal()

    await send_deal_alerts(bot, conn, [deal])

    row = conn.execute(
        "SELECT notified_at FROM ebay_listings WHERE item_id = ?", ("item-1",)
    ).fetchone()
    assert row["notified_at"] is not None


@pytest.mark.asyncio
async def test_send_error_continues(conn):
    """If send_message raises, the error is caught and other deals proceed."""
    db.add_search(conn, chat_id=111, query="jazz", min_deal_score=0.25)
    bot = AsyncMock()
    bot.send_message.side_effect = [Exception("network error"), None]
    deal1 = _make_deal(item_id="item-1")
    deal2 = _make_deal(item_id="item-2")

    await send_deal_alerts(bot, conn, [deal1, deal2])

    assert bot.send_message.call_count == 2
    # Only deal2 should be logged (deal1 failed)
    assert not db.was_alerted(conn, 111, "item-1")
    assert db.was_alerted(conn, 111, "item-2")
