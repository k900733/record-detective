"""Tests for eBay UPC/catalog extraction helpers."""

from vinyl_detective.ebay import (
    extract_catalog_no_from_title,
    extract_upc,
    normalize_catalog,
)


def test_extract_upc_found():
    aspects = [{"name": "UPC", "value": "123456789"}]
    assert extract_upc(aspects) == "123456789"


def test_extract_upc_ean():
    aspects = [{"name": "EAN", "value": "4988009012345"}]
    assert extract_upc(aspects) == "4988009012345"


def test_extract_upc_not_found():
    aspects = [{"name": "Color", "value": "Black"}]
    assert extract_upc(aspects) is None


def test_extract_upc_empty():
    assert extract_upc([]) is None


def test_extract_catalog_blp():
    assert extract_catalog_no_from_title(
        "Blue Note BLP-4003 Art Blakey Vinyl LP"
    ) == "BLP-4003"


def test_extract_catalog_mfsl():
    assert extract_catalog_no_from_title(
        "MFSL 1-234 Miles Davis Kind Of Blue"
    ) == "MFSL 1-234"


def test_extract_catalog_app():
    assert extract_catalog_no_from_title(
        "APP 3014 Analogue Productions Reissue"
    ) == "APP 3014"


def test_extract_catalog_none():
    assert extract_catalog_no_from_title("rare jazz vinyl lot") is None


def test_normalize_catalog_dash():
    assert normalize_catalog("BLP-4003") == "BLP4003"


def test_normalize_catalog_space_dash():
    assert normalize_catalog("MFSL 1-234") == "MFSL1234"


def test_normalize_catalog_dots_underscores():
    assert normalize_catalog("SR_V.100") == "SRV100"
