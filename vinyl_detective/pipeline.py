"""Scan-match-score pipeline: ties eBay search, matcher, and scorer together."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

from vinyl_detective.ebay import (
    EbayClient,
    extract_catalog_no_from_title,
    extract_upc,
)
from vinyl_detective.matcher import match_listing
from vinyl_detective.scorer import Deal, score_deal
from vinyl_detective.db import upsert_listing, update_listing_match

log = logging.getLogger(__name__)


async def scan_and_score(
    ebay_client: EbayClient,
    conn: sqlite3.Connection,
    search_query: str,
) -> list[Deal]:
    """Search eBay, match against Discogs DB, score deals.

    For each listing:
    1. Try catalog-number extraction from title first (free).
    2. Only call get_item for UPC enrichment if no catalog number found.
    3. Run the 3-tier matcher; skip if no match.
    4. Score the deal; skip if overpriced / no price data.
    5. Persist listing + match to DB.
    """
    listings = await ebay_client.search_listings(search_query)
    if not listings:
        return []

    deals: list[Deal] = []
    for listing in listings:
        upc = None
        catalog_no = extract_catalog_no_from_title(listing["title"])
        if catalog_no is None:
            item_detail = await ebay_client.get_item(listing["item_id"])
            if item_detail is not None:
                upc = extract_upc(item_detail.get("localized_aspects", []))

        result = match_listing(conn, listing["title"], upc=upc)
        if result is None:
            continue

        deal = score_deal(listing, result)
        if deal is None:
            continue

        upsert_listing(
            conn,
            item_id=listing["item_id"],
            title=listing["title"],
            price=listing["price"],
            shipping=listing.get("shipping", 0),
            condition=listing.get("condition"),
            seller_rating=listing.get("seller_rating"),
        )
        update_listing_match(
            conn,
            item_id=listing["item_id"],
            match_release_id=result.release_id,
            match_method=result.method,
            match_score=result.score,
            deal_score=deal.deal_score,
        )
        deals.append(deal)

    log.info("scan_and_score(%r): %d listings -> %d deals", search_query, len(listings), len(deals))
    return deals


async def poll_ebay_loop(ebay_client, conn, bot, config):
    """Poll eBay for deals on all active saved searches, send alerts, repeat."""
    from vinyl_detective.db import get_active_searches
    from vinyl_detective.telegram_bot import send_deal_alerts

    while True:
        try:
            searches = get_active_searches(conn)
            for search in searches:
                deals = await scan_and_score(ebay_client, conn, search["query"])
                filtered = [
                    d for d in deals
                    if d.deal_score >= search["min_deal_score"]
                ]
                if filtered:
                    await send_deal_alerts(
                        bot, conn, filtered, config.affiliate_campaign_id
                    )
                log.info(
                    "poll_ebay: search=%r found %d deals (%d after filter)",
                    search["query"],
                    len(deals),
                    len(filtered),
                )
        except Exception:
            log.exception("poll_ebay_loop iteration failed")
        await asyncio.sleep(config.ebay_poll_minutes * 60)


async def refresh_discogs_loop(discogs_client, conn, config):
    """Periodically refresh stale Discogs price data."""
    from vinyl_detective.discogs import refresh_stale_prices

    while True:
        try:
            count = await refresh_stale_prices(
                discogs_client, conn, max_age_days=config.discogs_refresh_days
            )
            log.info("refresh_discogs: refreshed %d releases", count)
        except Exception:
            log.exception("refresh_discogs_loop iteration failed")
        await asyncio.sleep(24 * 60 * 60)
