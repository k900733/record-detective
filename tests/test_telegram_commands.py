"""Tests for Telegram bot command handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vinyl_detective import db
from vinyl_detective.telegram_bot import (
    _add_search,
    _help,
    _my_searches,
    _remove_search,
    _set_threshold,
    _start,
    create_bot,
)


@pytest.fixture()
def conn():
    c = db.init_db(":memory:")
    yield c
    c.close()


def _make_update(chat_id=12345):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    return update


def _make_context(conn, args=None):
    ctx = MagicMock()
    ctx.bot_data = {"db": conn}
    ctx.args = args or []
    return ctx


@pytest.mark.asyncio
async def test_start_sends_welcome(conn):
    update = _make_update()
    ctx = _make_context(conn)
    await _start(update, ctx)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Vinyl Detective" in text
    assert "/add_search" in text


@pytest.mark.asyncio
async def test_help_lists_commands(conn):
    update = _make_update()
    ctx = _make_context(conn)
    await _help(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "/start" in text
    assert "/add_search" in text
    assert "/remove_search" in text
    assert "/set_threshold" in text


@pytest.mark.asyncio
async def test_add_search_creates_entry(conn):
    update = _make_update(chat_id=99)
    ctx = _make_context(conn, args=["blue", "note", "jazz"])
    await _add_search(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "blue note jazz" in text

    searches = db.get_searches_for_chat(conn, 99)
    assert len(searches) == 1
    assert searches[0]["query"] == "blue note jazz"


@pytest.mark.asyncio
async def test_add_search_no_args(conn):
    update = _make_update()
    ctx = _make_context(conn, args=[])
    await _add_search(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_my_searches_lists_searches(conn):
    db.add_search(conn, 99, "miles davis")
    db.add_search(conn, 99, "coltrane")
    update = _make_update(chat_id=99)
    ctx = _make_context(conn)
    await _my_searches(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "miles davis" in text
    assert "coltrane" in text


@pytest.mark.asyncio
async def test_my_searches_empty(conn):
    update = _make_update(chat_id=999)
    ctx = _make_context(conn)
    await _my_searches(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "No saved searches" in text


@pytest.mark.asyncio
async def test_remove_search_deactivates(conn):
    sid = db.add_search(conn, 99, "test query")
    update = _make_update(chat_id=99)
    ctx = _make_context(conn, args=[str(sid)])
    await _remove_search(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert str(sid) in text
    assert "removed" in text.lower()

    searches = db.get_searches_for_chat(conn, 99)
    assert searches[0]["active"] == 0


@pytest.mark.asyncio
async def test_remove_search_no_args(conn):
    update = _make_update()
    ctx = _make_context(conn, args=[])
    await _remove_search(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_set_threshold_updates_all_searches(conn):
    db.add_search(conn, 99, "query1")
    db.add_search(conn, 99, "query2")
    update = _make_update(chat_id=99)
    ctx = _make_context(conn, args=["0.50"])
    await _set_threshold(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "0.50" in text

    searches = db.get_searches_for_chat(conn, 99)
    for s in searches:
        assert s["min_deal_score"] == 0.50


@pytest.mark.asyncio
async def test_set_threshold_out_of_range(conn):
    update = _make_update()
    ctx = _make_context(conn, args=["1.5"])
    await _set_threshold(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "between" in text.lower()


@pytest.mark.asyncio
async def test_create_bot_returns_application(conn):
    with patch("vinyl_detective.telegram_bot.Application") as mock_app_cls:
        mock_builder = MagicMock()
        mock_app = MagicMock()
        mock_app.bot_data = {}
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app

        mock_app_cls.builder.return_value = mock_builder

        app = create_bot("fake-token", conn)
        mock_builder.token.assert_called_once_with("fake-token")
        assert app.bot_data["db"] is conn
        assert mock_app.add_handler.call_count == 6
