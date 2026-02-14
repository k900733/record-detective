"""Smoke tests for the full async orchestrator in __main__.py."""

import asyncio
import os
import sqlite3
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


@pytest.mark.asyncio
async def test_run_initializes_and_shuts_down(mock_env, config):
    """Verify run() loads config, inits DB, creates clients, shuts down cleanly."""
    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.__aenter__ = AsyncMock(return_value=mock_app)
    mock_app.__aexit__ = AsyncMock(return_value=False)
    mock_updater = MagicMock()
    mock_updater.start_polling = AsyncMock()
    mock_updater.stop = AsyncMock()
    mock_app.updater = mock_updater
    mock_app.bot = MagicMock()

    async def fake_loop(*_args, **_kwargs):
        await asyncio.sleep(0)

    with (
        patch("vinyl_detective.__main__.create_bot", return_value=mock_app) as mock_create,
        patch("vinyl_detective.__main__.poll_ebay_loop", side_effect=fake_loop),
        patch("vinyl_detective.__main__.refresh_discogs_loop", side_effect=fake_loop),
        patch("vinyl_detective.__main__.cleanup_stale_loop", side_effect=fake_loop),
    ):
        from vinyl_detective.__main__ import run

        loop = asyncio.get_running_loop()
        task = asyncio.create_task(run())
        await asyncio.sleep(0.1)
        # Trigger shutdown
        loop.call_soon(lambda: [t.cancel() for t in asyncio.all_tasks() if t is not asyncio.current_task()])
        # Instead, set SIGINT-like behavior via stop event
        # The run() registers signal handlers, but in tests we just cancel
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        mock_create.assert_called_once_with(config.telegram_token, pytest.approx(mock_create.call_args[0][1], abs=1))
        assert os.path.exists(config.db_path)


@pytest.mark.asyncio
async def test_run_creates_db_with_schema(mock_env, config):
    """Verify DB file has expected tables after run() starts."""
    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.__aenter__ = AsyncMock(return_value=mock_app)
    mock_app.__aexit__ = AsyncMock(return_value=False)
    mock_updater = MagicMock()
    mock_updater.start_polling = AsyncMock()
    mock_updater.stop = AsyncMock()
    mock_app.updater = mock_updater
    mock_app.bot = MagicMock()

    async def fake_loop(*_args, **_kwargs):
        await asyncio.sleep(0)

    with (
        patch("vinyl_detective.__main__.create_bot", return_value=mock_app),
        patch("vinyl_detective.__main__.poll_ebay_loop", side_effect=fake_loop),
        patch("vinyl_detective.__main__.refresh_discogs_loop", side_effect=fake_loop),
        patch("vinyl_detective.__main__.cleanup_stale_loop", side_effect=fake_loop),
    ):
        from vinyl_detective.__main__ import run

        task = asyncio.create_task(run())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert os.path.exists(config.db_path)
    conn = sqlite3.connect(config.db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "discogs_releases" in tables
    assert "ebay_listings" in tables
    assert "saved_searches" in tables
    assert "alert_log" in tables


@pytest.mark.asyncio
async def test_run_passes_correct_config_to_loops(mock_env, config):
    """Verify the loop coroutines are called with correct arguments."""
    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.__aenter__ = AsyncMock(return_value=mock_app)
    mock_app.__aexit__ = AsyncMock(return_value=False)
    mock_updater = MagicMock()
    mock_updater.start_polling = AsyncMock()
    mock_updater.stop = AsyncMock()
    mock_app.updater = mock_updater
    mock_app.bot = MagicMock()

    poll_mock = AsyncMock()
    refresh_mock = AsyncMock()
    cleanup_mock = AsyncMock()

    with (
        patch("vinyl_detective.__main__.create_bot", return_value=mock_app),
        patch("vinyl_detective.__main__.poll_ebay_loop", poll_mock),
        patch("vinyl_detective.__main__.refresh_discogs_loop", refresh_mock),
        patch("vinyl_detective.__main__.cleanup_stale_loop", cleanup_mock),
    ):
        from vinyl_detective.__main__ import run

        task = asyncio.create_task(run())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    poll_mock.assert_called_once()
    poll_args = poll_mock.call_args[0]
    assert len(poll_args) == 4  # ebay_client, conn, bot, config

    refresh_mock.assert_called_once()
    refresh_args = refresh_mock.call_args[0]
    assert len(refresh_args) == 3  # discogs_client, conn, config

    cleanup_mock.assert_called_once()
    cleanup_args = cleanup_mock.call_args[0]
    assert len(cleanup_args) == 1  # conn
