"""Tests for telegram_bot.format_deal_message."""

from vinyl_detective.matcher import MatchResult
from vinyl_detective.scorer import Deal
from vinyl_detective.telegram_bot import format_deal_message


def _make_deal(condition="Very Good Plus (VG+)"):
    match = MatchResult(
        release_id=123,
        artist="Art Blakey",
        title="Moanin'",
        median_price=50.0,
        method="catalog_no",
        score=1.0,
    )
    return Deal(
        item_id="abc",
        ebay_title="Art Blakey Moanin BLP-4003",
        ebay_price=20.0,
        shipping=3.99,
        condition=condition,
        seller_rating=99.5,
        match=match,
        deal_score=0.52,
        priority="high",
        item_web_url="https://ebay.com/itm/abc",
    )


def test_format_contains_key_info():
    deal = _make_deal()
    url = "https://ebay.com/itm/abc?aff=1"
    msg = format_deal_message(deal, url)

    assert "Art Blakey" in msg
    assert "Moanin" in msg
    assert "$20.00" in msg
    assert "$3.99" in msg
    assert "$50.00" in msg
    assert "52%" in msg
    assert url in msg
    assert "[HIGH]" in msg


def test_format_has_html_tags():
    deal = _make_deal()
    msg = format_deal_message(deal, "https://ebay.com/itm/abc")

    assert "<b>" in msg
    assert '<a href="' in msg


def test_format_condition_none():
    deal = _make_deal(condition=None)
    msg = format_deal_message(deal, "https://ebay.com/itm/abc")

    assert "Condition" not in msg
    assert "Art Blakey" in msg
