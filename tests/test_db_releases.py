"""Tests for db.py discogs_releases CRUD helpers."""

import time

from vinyl_detective.db import (
    init_db,
    upsert_release,
    get_release,
    get_stale_releases,
    lookup_by_catalog,
    lookup_by_barcode,
)


def _make_db():
    return init_db(":memory:")


def test_upsert_and_get_release():
    conn = _make_db()
    upsert_release(conn, 123, "Miles Davis", "Kind of Blue",
                   catalog_no="CS-8163", barcode="074646585012",
                   format_="Vinyl", median_price=45.0, low_price=30.0)
    r = get_release(conn, 123)
    assert r is not None
    assert r["artist"] == "Miles Davis"
    assert r["title"] == "Kind of Blue"
    assert r["catalog_no"] == "CS-8163"
    assert r["barcode"] == "074646585012"
    assert r["format"] == "Vinyl"
    assert r["median_price"] == 45.0
    assert r["low_price"] == 30.0
    assert r["updated_at"] is not None


def test_upsert_updates_existing():
    conn = _make_db()
    upsert_release(conn, 123, "Miles Davis", "Kind of Blue",
                   median_price=45.0)
    upsert_release(conn, 123, "Miles Davis", "Kind of Blue",
                   median_price=50.0)
    r = get_release(conn, 123)
    assert r["median_price"] == 50.0


def test_get_stale_releases():
    conn = _make_db()
    upsert_release(conn, 1, "A", "B", median_price=10.0)
    # Backdate updated_at to 30 days ago
    old_ts = int(time.time()) - 30 * 86400
    conn.execute(
        "UPDATE discogs_releases SET updated_at = ? WHERE release_id = ?",
        (old_ts, 1),
    )
    conn.commit()
    stale = get_stale_releases(conn, max_age_days=7)
    assert any(r["release_id"] == 1 for r in stale)


def test_get_stale_releases_null_updated():
    conn = _make_db()
    upsert_release(conn, 2, "X", "Y")
    # Force updated_at to NULL
    conn.execute(
        "UPDATE discogs_releases SET updated_at = NULL WHERE release_id = ?",
        (2,),
    )
    conn.commit()
    stale = get_stale_releases(conn, max_age_days=7)
    assert any(r["release_id"] == 2 for r in stale)


def test_lookup_by_catalog_exact():
    conn = _make_db()
    upsert_release(conn, 10, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003")
    assert lookup_by_catalog(conn, "BLP4003") is None  # no normalization
    r = lookup_by_catalog(conn, "BLP-4003")
    assert r is not None
    assert r["release_id"] == 10


def test_lookup_by_barcode():
    conn = _make_db()
    upsert_release(conn, 20, "Coltrane", "Blue Train",
                   barcode="123456789")
    r = lookup_by_barcode(conn, "123456789")
    assert r is not None
    assert r["release_id"] == 20
    assert lookup_by_barcode(conn, "000000000") is None


def test_get_release_not_found():
    conn = _make_db()
    assert get_release(conn, 99999) is None
