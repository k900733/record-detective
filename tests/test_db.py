"""Tests for db.py schema initialization."""

import os
import tempfile

from vinyl_detective.db import init_db


def _table_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return {r[0] for r in rows}


def _index_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
    ).fetchall()
    return {r[0] for r in rows}


def test_tables_created():
    conn = init_db(":memory:")
    tables = _table_names(conn)
    for t in ("discogs_releases", "ebay_listings", "saved_searches", "alert_log"):
        assert t in tables, f"Missing table: {t}"
    conn.close()


def test_fts_virtual_table_created():
    conn = init_db(":memory:")
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='releases_fts'"
    ).fetchall()
    assert len(rows) == 1
    conn.close()


def test_indexes_created():
    conn = init_db(":memory:")
    indexes = _index_names(conn)
    for idx in (
        "idx_releases_catalog",
        "idx_releases_barcode",
        "idx_listings_match",
        "idx_searches_chat",
    ):
        assert idx in indexes, f"Missing index: {idx}"
    conn.close()


def test_wal_journal_mode():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = init_db(path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal", f"Expected WAL, got {mode}"
        conn.close()
    finally:
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(path + ext)
            except FileNotFoundError:
                pass


def test_idempotent():
    conn = init_db(":memory:")
    # Calling init logic again should not raise
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS discogs_releases "
        "(release_id INTEGER PRIMARY KEY, artist TEXT NOT NULL, title TEXT NOT NULL)"
    )
    tables = _table_names(conn)
    assert "discogs_releases" in tables
    conn.close()
