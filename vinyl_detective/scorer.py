"""Deal scoring logic for eBay listings matched against Discogs prices."""

from dataclasses import dataclass

from vinyl_detective.matcher import MatchResult


@dataclass(frozen=True)
class Deal:
    item_id: str
    ebay_title: str
    ebay_price: float
    shipping: float
    condition: str | None
    seller_rating: float | None
    match: MatchResult
    deal_score: float
    priority: str  # "high", "medium", or "low"
    item_web_url: str


def score_deal(ebay_listing: dict, match: MatchResult) -> Deal | None:
    """Score an eBay listing against its Discogs match.

    Returns None if no median price available or listing is overpriced.
    """
    if match.median_price is None or match.median_price <= 0:
        return None

    total_price = ebay_listing["price"] + ebay_listing.get("shipping", 0)
    deal_score = (match.median_price - total_price) / match.median_price

    if deal_score < 0:
        return None

    if deal_score >= 0.40:
        priority = "high"
    elif deal_score >= 0.25:
        priority = "medium"
    else:
        priority = "low"

    return Deal(
        item_id=ebay_listing["item_id"],
        ebay_title=ebay_listing["title"],
        ebay_price=ebay_listing["price"],
        shipping=ebay_listing.get("shipping", 0),
        condition=ebay_listing.get("condition"),
        seller_rating=ebay_listing.get("seller_rating"),
        match=match,
        deal_score=deal_score,
        priority=priority,
        item_web_url=ebay_listing["item_web_url"],
    )


def filter_deals(deals: list[Deal], min_score: float = 0.25) -> list[Deal]:
    """Filter deals by minimum score and sort best-first."""
    return sorted(
        [d for d in deals if d.deal_score >= min_score],
        key=lambda d: d.deal_score,
        reverse=True,
    )
