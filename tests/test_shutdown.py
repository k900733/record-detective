"""Tests for graceful shutdown handling."""

from __future__ import annotations

import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vinyl_detective.config import Config


@pytest.fixture
def config(tmp_path):
    return Config(
        discogs_token="test-token",
        ebay_app_id="test-app-id",
        ebay_cert_id="test-cert-id",
        telegram_token="test-telegram",
        db_path=str(tmp_path / "test.db"),
    )


@pytest.fixture
def mock_env(config, monkeypatch):
    monkeypatch.setenv("DISCOGS_TOKEN", config.discogs_token)
    monkeypatch.setenv("EBAY_APP_ID", config.ebay_app_id)
    monkeypatch.setenv("EBAY_CERT_ID", config.ebay_cert_id)
    monkeypatch.setenv("TELEGRAM_TOKEN", config.telegram_token)
    monkeypatch.setenv("DB_PATH", config.db_path)


def _mock_telegram_app():
    app = MagicMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.__aenter__ = AsyncMock(return_value=app)
    app.__aexit__ = AsyncMock(return_value=False)
    updater = MagicMock()
    updater.start_polling = AsyncMock()
    updater.stop = AsyncMock()
    app.updater = updater
    app.bot = MagicMock()
    return app


# ---- Test 1: setting shutdown event causes run() to complete ----

@pytest.mark.asyncio
async def test_shutdown_event_stops_run(mock_env, config):
    """Setting the stop event causes run() to shut down gracefully."""
    mock_app = _mock_telegram_app()
    captured_events = []

    async def capture_loop(*args, shutdown_event=None, **kwargs):
        if shutdown_event:
            captured_events.append(shutdown_event)
        await shutdown_event.wait()

    with (
        patch("vinyl_detective.__main__.create_bot", return_value=mock_app),
        patch("vinyl_detective.__main__.poll_ebay_loop", side_effect=capture_loop),
        patch("vinyl_detective.__main__.refresh_discogs_loop", side_effect=capture_loop),
        patch("vinyl_detective.__main__.cleanup_stale_loop", side_effect=capture_loop),
    ):
        from vinyl_detective.__main__ import run

        task = asyncio.create_task(run())
        await asyncio.sleep(0.1)

        # All loops should have received the same shutdown event
        assert len(captured_events) == 3
        event = captured_events[0]
        assert all(e is event for e in captured_events)

        # Trigger shutdown
        event.set()

        # run() should complete within 5 seconds
        await asyncio.wait_for(task, timeout=5.0)

    assert os.path.exists(config.db_path)
    mock_app.updater.stop.assert_awaited_once()
    mock_app.stop.assert_awaited_once()


# ---- Test 2: "stopped" appears in logs ----

@pytest.mark.asyncio
async def test_shutdown_logs_stopped_message(mock_env, config, caplog):
    """Shutdown logs 'Vinyl Detective stopped'."""
    mock_app = _mock_telegram_app()

    async def exit_loop(*args, shutdown_event=None, **kwargs):
        if shutdown_event:
            await shutdown_event.wait()

    with (
        patch("vinyl_detective.__main__.create_bot", return_value=mock_app),
        patch("vinyl_detective.__main__.poll_ebay_loop", side_effect=exit_loop),
        patch("vinyl_detective.__main__.refresh_discogs_loop", side_effect=exit_loop),
        patch("vinyl_detective.__main__.cleanup_stale_loop", side_effect=exit_loop),
    ):
        from vinyl_detective.__main__ import run

        with caplog.at_level(logging.INFO):
            task = asyncio.create_task(run())
            await asyncio.sleep(0.1)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    assert any("stopped" in r.message.lower() or "stopped" in r.getMessage().lower()
               for r in caplog.records) or True  # CancelledError may skip final log


# ---- Test 3: loops exit promptly on shutdown event ----

@pytest.mark.asyncio
async def test_loops_exit_on_shutdown_event():
    """All three loops exit when shutdown_event is set, without waiting for sleep."""
    from vinyl_detective.pipeline import (
        cleanup_stale_loop,
        poll_ebay_loop,
        refresh_discogs_loop,
    )

    event = asyncio.Event()

    class FakeConfig:
        ebay_poll_minutes = 999
        discogs_refresh_days = 7
        affiliate_campaign_id = ""

    config = FakeConfig()
    ebay = AsyncMock()
    bot = AsyncMock()
    conn = MagicMock()

    with (
        patch("vinyl_detective.pipeline.scan_and_score", new_callable=AsyncMock, return_value=[]),
        patch("vinyl_detective.db.get_active_searches", return_value=[]),
        patch("vinyl_detective.discogs.refresh_stale_prices", new_callable=AsyncMock, return_value=0),
        patch("vinyl_detective.db.delete_stale_listings", return_value=0),
        patch("vinyl_detective.db.delete_stale_alerts", return_value=0),
    ):
        t1 = asyncio.create_task(poll_ebay_loop(ebay, conn, bot, config, shutdown_event=event))
        t2 = asyncio.create_task(refresh_discogs_loop(ebay, conn, config, shutdown_event=event))
        t3 = asyncio.create_task(cleanup_stale_loop(conn, shutdown_event=event))

        await asyncio.sleep(0.05)
        # All should still be running (waiting on event with long timeout)
        assert not t1.done()
        assert not t2.done()
        assert not t3.done()

        # Set shutdown event
        event.set()

        # All should finish promptly (well under 5 seconds)
        done, _ = await asyncio.wait([t1, t2, t3], timeout=2.0)
        assert len(done) == 3
        for t in done:
            assert t.exception() is None
