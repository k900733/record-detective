"""Tests for deal scoring logic."""

from vinyl_detective.matcher import MatchResult
from vinyl_detective.scorer import score_deal


def _make_match(median_price=50.0):
    return MatchResult(
        release_id=123,
        artist="Art Blakey",
        title="Moanin'",
        median_price=median_price,
        method="catalog_no",
        score=1.0,
    )


def _make_listing(**overrides):
    defaults = {
        "item_id": "ebay-001",
        "title": "Art Blakey Moanin LP",
        "price": 20.0,
        "shipping": 0,
        "condition": "Very Good Plus (VG+)",
        "seller_rating": 99.5,
        "item_web_url": "https://ebay.com/itm/001",
    }
    defaults.update(overrides)
    return defaults


def test_high_priority_deal():
    """$20 listing, $50 median, $0 shipping -> 60% savings, high priority."""
    deal = score_deal(_make_listing(price=20.0, shipping=0), _make_match(50.0))
    assert deal is not None
    assert deal.deal_score == 0.6
    assert deal.priority == "high"


def test_low_priority_deal():
    """$35 listing + $5 shipping = $40 total, $50 median -> 20% savings, low."""
    deal = score_deal(_make_listing(price=35.0, shipping=5.0), _make_match(50.0))
    assert deal is not None
    assert deal.deal_score == 0.2
    assert deal.priority == "low"


def test_high_priority_boundary():
    """$30 listing, $50 median -> exactly 40% savings, high priority."""
    deal = score_deal(_make_listing(price=30.0, shipping=0), _make_match(50.0))
    assert deal is not None
    assert deal.deal_score == 0.4
    assert deal.priority == "high"


def test_overpriced_returns_none():
    """$60 listing, $50 median -> overpriced, returns None."""
    deal = score_deal(_make_listing(price=60.0), _make_match(50.0))
    assert deal is None


def test_no_median_price_returns_none():
    """Match with median_price=None -> returns None."""
    deal = score_deal(_make_listing(), _make_match(median_price=None))
    assert deal is None
