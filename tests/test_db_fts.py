"""Tests for FTS5 search in db.py (Plan 1, Step 6)."""

from vinyl_detective.db import fts5_search, init_db, upsert_release


def _seed(conn):
    upsert_release(conn, 1, "Miles Davis", "Kind of Blue", catalog_no="CS-8163")
    upsert_release(conn, 2, "John Coltrane", "Blue Train", catalog_no="BLP-1577")
    upsert_release(
        conn, 3, "Thelonious Monk", "Brilliant Corners", catalog_no="RLP-12-226"
    )


def test_search_miles_davis_blue():
    conn = init_db(":memory:")
    _seed(conn)
    results = fts5_search(conn, "Miles Davis Blue")
    titles = [r["title"] for r in results]
    assert "Kind of Blue" in titles


def test_search_coltrane_train():
    conn = init_db(":memory:")
    _seed(conn)
    results = fts5_search(conn, "Coltrane Train")
    titles = [r["title"] for r in results]
    assert "Blue Train" in titles


def test_search_nonexistent():
    conn = init_db(":memory:")
    _seed(conn)
    results = fts5_search(conn, "xyznonexistent")
    assert results == []


def test_search_empty_query():
    conn = init_db(":memory:")
    _seed(conn)
    assert fts5_search(conn, "") == []
    assert fts5_search(conn, "   ") == []


def test_search_returns_expected_fields():
    conn = init_db(":memory:")
    _seed(conn)
    results = fts5_search(conn, "Monk")
    assert len(results) >= 1
    row = results[0]
    for key in ("release_id", "artist", "title", "catalog_no", "median_price"):
        assert key in row
