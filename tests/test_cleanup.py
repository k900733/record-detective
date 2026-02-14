"""Tests for the cleanup loop and DB cleanup functions."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from vinyl_detective.db import (
    delete_stale_alerts,
    delete_stale_listings,
    init_db,
    upsert_listing,
)
from vinyl_detective.pipeline import cleanup_stale_loop


# ---- helpers ----

def _setup_db(tmp_path):
    db = tmp_path / "test.db"
    conn = init_db(str(db))
    return conn


# ---- Test 1: old listings deleted, recent kept ----

def test_delete_stale_listings(tmp_path):
    conn = _setup_db(tmp_path)
    now = int(time.time())
    # 60-day-old listing
    upsert_listing(conn, "OLD1", "Old Record", 10.0, first_seen=now - 60 * 86400)
    # 5-day-old listing
    upsert_listing(conn, "NEW1", "New Record", 15.0, first_seen=now - 5 * 86400)

    deleted = delete_stale_listings(conn, max_age_days=30)

    assert deleted == 1
    rows = conn.execute("SELECT item_id FROM ebay_listings").fetchall()
    assert [r["item_id"] for r in rows] == ["NEW1"]


# ---- Test 2: old alerts deleted, recent kept ----

def test_delete_stale_alerts(tmp_path):
    conn = _setup_db(tmp_path)
    now = int(time.time())
    # Manually insert with controlled sent_at
    conn.execute(
        "INSERT INTO alert_log (chat_id, item_id, sent_at, deal_score) VALUES (?,?,?,?)",
        (1, "ITEM_OLD", now - 100 * 86400, 0.5),
    )
    conn.execute(
        "INSERT INTO alert_log (chat_id, item_id, sent_at, deal_score) VALUES (?,?,?,?)",
        (1, "ITEM_NEW", now - 10 * 86400, 0.4),
    )
    conn.commit()

    deleted = delete_stale_alerts(conn, max_age_days=90)

    assert deleted == 1
    rows = conn.execute("SELECT item_id FROM alert_log").fetchall()
    assert [r["item_id"] for r in rows] == ["ITEM_NEW"]


# ---- Test 3: cleanup loop calls both functions ----

@pytest.mark.asyncio
async def test_cleanup_loop_calls_delete_functions(tmp_path):
    conn = _setup_db(tmp_path)

    async def cancel_after_one(_):
        raise asyncio.CancelledError

    with patch(
        "vinyl_detective.db.delete_stale_listings", return_value=2
    ) as mock_listings, patch(
        "vinyl_detective.db.delete_stale_alerts", return_value=1
    ) as mock_alerts, patch(
        "vinyl_detective.pipeline.asyncio.sleep", side_effect=cancel_after_one
    ):
        with pytest.raises(asyncio.CancelledError):
            await cleanup_stale_loop(conn)

        mock_listings.assert_called_once_with(conn, max_age_days=30)
        mock_alerts.assert_called_once_with(conn, max_age_days=90)


# ---- Test 4: exception doesn't crash the loop ----

@pytest.mark.asyncio
async def test_cleanup_loop_resilient_to_errors(tmp_path):
    conn = _setup_db(tmp_path)
    iteration = 0

    async def fake_sleep(_):
        nonlocal iteration
        iteration += 1
        if iteration >= 2:
            raise asyncio.CancelledError

    with patch(
        "vinyl_detective.db.delete_stale_listings",
        side_effect=[RuntimeError("disk full"), 0],
    ) as mock_listings, patch(
        "vinyl_detective.db.delete_stale_alerts", return_value=0
    ), patch(
        "vinyl_detective.pipeline.asyncio.sleep", side_effect=fake_sleep
    ):
        with pytest.raises(asyncio.CancelledError):
            await cleanup_stale_loop(conn)

        assert mock_listings.call_count == 2
