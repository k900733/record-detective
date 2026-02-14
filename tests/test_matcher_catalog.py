"""Tests for Tier 1 catalog number matching."""

from vinyl_detective.db import init_db, upsert_release
from vinyl_detective.matcher import match_by_catalog


def _make_db():
    return init_db(":memory:")


def test_exact_catalog_match():
    conn = _make_db()
    upsert_release(conn, 1001, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003", median_price=80.0)
    result = match_by_catalog(conn, "Art Blakey Moanin Blue Note BLP-4003 Vinyl LP")
    assert result is not None
    assert result.method == "catalog_no"
    assert result.release_id == 1001
    assert result.artist == "Art Blakey"
    assert result.score == 1.0


def test_no_catalog_in_title():
    conn = _make_db()
    upsert_release(conn, 1001, "Art Blakey", "Moanin'",
                   catalog_no="BLP-4003")
    result = match_by_catalog(conn, "Art Blakey Moanin Vinyl LP")
    assert result is None


def test_normalized_catalog_match():
    conn = _make_db()
    upsert_release(conn, 2001, "Various", "Audiophile Press",
                   catalog_no="MFSL 1-234", median_price=120.0)
    result = match_by_catalog(conn, "Mobile Fidelity MFSL1-234 Original Vinyl")
    assert result is not None
    assert result.method == "catalog_no"
    assert result.release_id == 2001


def test_no_match_in_db():
    conn = _make_db()
    upsert_release(conn, 3001, "X", "Y", catalog_no="ABC-999")
    result = match_by_catalog(conn, "Some Title BLP-4003 Vinyl")
    assert result is None
