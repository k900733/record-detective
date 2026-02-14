from vinyl_detective.db import init_db, upsert_release
from vinyl_detective.matcher import match_by_fuzzy


def _make_db():
    conn = init_db(":memory:")
    releases = [
        dict(release_id=1, artist="Miles Davis", title="Kind of Blue",
             catalog_no="CS-8163", median_price=45.0, low_price=20.0),
        dict(release_id=2, artist="John Coltrane", title="A Love Supreme",
             catalog_no="AS-77", median_price=80.0, low_price=40.0),
        dict(release_id=3, artist="Thelonious Monk", title="Brilliant Corners",
             catalog_no="RLP-226", median_price=100.0, low_price=55.0),
    ]
    for r in releases:
        upsert_release(conn, **r)
    return conn


def test_fuzzy_match_miles_davis():
    conn = _make_db()
    result = match_by_fuzzy(conn, "Miles Davis Kind Blue")
    assert result is not None
    assert result.artist == "Miles Davis"
    assert result.method == "fuzzy"
    assert result.score >= 0.85


def test_fuzzy_no_match_unrelated():
    conn = _make_db()
    result = match_by_fuzzy(conn, "totally unrelated electronics product")
    assert result is None


def test_fuzzy_match_coltrane():
    conn = _make_db()
    result = match_by_fuzzy(conn, "Coltrane Love Supreme")
    assert result is not None
    assert result.title == "A Love Supreme"
    assert result.method == "fuzzy"
    assert result.score >= 0.85


def test_fuzzy_empty_db():
    conn = init_db(":memory:")
    result = match_by_fuzzy(conn, "Miles Davis Kind Of Blue")
    assert result is None
