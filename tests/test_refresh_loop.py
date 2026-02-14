"""Tests for the Discogs refresh loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from vinyl_detective.pipeline import refresh_discogs_loop


@dataclass(frozen=True)
class FakeConfig:
    discogs_refresh_days: int = 7


# ---- Test 1: calls refresh_stale_prices with correct max_age_days ----

@pytest.mark.asyncio
async def test_refresh_loop_calls_refresh_stale_prices():
    """Loop calls refresh_stale_prices with config's discogs_refresh_days."""
    config = FakeConfig(discogs_refresh_days=14)
    discogs = AsyncMock()
    conn = object()

    async def cancel_after_one(_):
        raise asyncio.CancelledError

    with patch(
        "vinyl_detective.discogs.refresh_stale_prices",
        new_callable=AsyncMock,
        return_value=5,
    ) as mock_refresh, patch(
        "vinyl_detective.pipeline.asyncio.sleep",
        side_effect=cancel_after_one,
    ):
        with pytest.raises(asyncio.CancelledError):
            await refresh_discogs_loop(discogs, conn, config)

        mock_refresh.assert_called_once_with(
            discogs, conn, max_age_days=14
        )


# ---- Test 2: exception doesn't crash the loop ----

@pytest.mark.asyncio
async def test_refresh_loop_resilient_to_errors():
    """An exception in refresh_stale_prices is caught; loop continues."""
    config = FakeConfig()
    discogs = AsyncMock()
    conn = object()

    iteration = 0

    async def fake_sleep(_):
        nonlocal iteration
        iteration += 1
        if iteration >= 2:
            raise asyncio.CancelledError

    with patch(
        "vinyl_detective.discogs.refresh_stale_prices",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("API down"), 3],
    ) as mock_refresh, patch(
        "vinyl_detective.pipeline.asyncio.sleep",
        side_effect=fake_sleep,
    ):
        with pytest.raises(asyncio.CancelledError):
            await refresh_discogs_loop(discogs, conn, config)

        assert mock_refresh.call_count == 2
