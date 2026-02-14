from vinyl_detective.matcher import MatchResult
from vinyl_detective.scorer import Deal, filter_deals


def _make_deal(score: float) -> Deal:
    match = MatchResult(
        release_id=1,
        artist="Artist",
        title="Title",
        median_price=50.0,
        method="catalog_no",
        score=1.0,
    )
    return Deal(
        item_id=f"item-{score}",
        ebay_title="Test LP",
        ebay_price=50.0 * (1 - score),
        shipping=0,
        condition=None,
        seller_rating=None,
        match=match,
        deal_score=score,
        priority="high" if score >= 0.40 else ("medium" if score >= 0.25 else "low"),
        item_web_url="https://ebay.com/itm/1",
    )


def test_filter_default_threshold():
    deals = [_make_deal(0.6), _make_deal(0.3), _make_deal(0.1)]
    result = filter_deals(deals, min_score=0.25)
    assert len(result) == 2
    assert result[0].deal_score == 0.6
    assert result[1].deal_score == 0.3


def test_filter_high_threshold():
    deals = [_make_deal(0.6), _make_deal(0.3), _make_deal(0.1)]
    result = filter_deals(deals, min_score=0.5)
    assert len(result) == 1
    assert result[0].deal_score == 0.6


def test_filter_empty_list():
    assert filter_deals([], min_score=0.25) == []
