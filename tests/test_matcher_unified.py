"""Tests for unified match_listing() function."""

from vinyl_detective.db import init_db, upsert_release
from vinyl_detective.matcher import match_listing


def _make_db():
    return init_db(":memory:")


def test_tier1_catalog_wins():
    conn = _make_db()
    upsert_release(conn, 1001, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003", barcode="074646868027",
                   median_price=80.0)
    result = match_listing(conn, "Art Blakey Moanin BLP-4003", upc="074646868027")
    assert result is not None
    assert result.method == "catalog_no"
    assert result.release_id == 1001
    assert result.score == 1.0


def test_tier2_barcode_when_no_catalog():
    conn = _make_db()
    upsert_release(conn, 1001, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003", barcode="074646868027",
                   median_price=80.0)
    result = match_listing(conn, "Art Blakey Moanin Vinyl", upc="074646868027")
    assert result is not None
    assert result.method == "barcode"
    assert result.release_id == 1001


def test_tier3_fuzzy_fallback():
    conn = _make_db()
    upsert_release(conn, 1001, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003", barcode="074646868027",
                   median_price=80.0)
    result = match_listing(conn, "Art Blakey Moanin", upc=None)
    assert result is not None
    assert result.method == "fuzzy"
    assert result.release_id == 1001
    assert result.score >= 0.85


def test_no_match():
    conn = _make_db()
    upsert_release(conn, 1001, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003", barcode="074646868027",
                   median_price=80.0)
    result = match_listing(conn, "random electronics gadget", upc=None)
    assert result is None
