from vinyl_detective.db import init_db, upsert_release
from vinyl_detective.matcher import match_by_barcode


def _make_db():
    return init_db(":memory:")


def test_barcode_match():
    conn = _make_db()
    upsert_release(conn, 2001, "Miles Davis", "Kind of Blue",
                   barcode="074646868027", median_price=50.0)
    result = match_by_barcode(conn, "074646868027")
    assert result is not None
    assert result.method == "barcode"
    assert result.release_id == 2001
    assert result.artist == "Miles Davis"
    assert result.score == 1.0


def test_no_barcode_in_db():
    conn = _make_db()
    upsert_release(conn, 2002, "Art Blakey", "Moanin'",
                   barcode="111111111111")
    result = match_by_barcode(conn, "000000000000")
    assert result is None


def test_none_upc():
    conn = _make_db()
    result = match_by_barcode(conn, None)
    assert result is None


def test_empty_upc():
    conn = _make_db()
    result = match_by_barcode(conn, "")
    assert result is None
