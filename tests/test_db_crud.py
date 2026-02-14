"""Tests for saved_searches, ebay_listings, and alert_log CRUD helpers."""

from vinyl_detective.db import (
    add_search,
    get_active_searches,
    get_searches_for_chat,
    get_unnotified_deals,
    init_db,
    log_alert,
    mark_notified,
    toggle_search,
    update_listing_match,
    upsert_listing,
    upsert_release,
    was_alerted,
)


def _make_db():
    return init_db(":memory:")


# -- saved_searches --

def test_add_and_get_active_search():
    conn = _make_db()
    sid = add_search(conn, chat_id=111, query="blue note vinyl")
    assert sid is not None
    active = get_active_searches(conn)
    assert len(active) == 1
    assert active[0]["query"] == "blue note vinyl"
    assert active[0]["chat_id"] == 111
    assert active[0]["min_deal_score"] == 0.25
    assert active[0]["poll_minutes"] == 30


def test_toggle_search_inactive():
    conn = _make_db()
    sid = add_search(conn, chat_id=111, query="jazz")
    toggle_search(conn, sid, active=False)
    assert get_active_searches(conn) == []


def test_toggle_search_reactivate():
    conn = _make_db()
    sid = add_search(conn, chat_id=111, query="jazz")
    toggle_search(conn, sid, active=False)
    toggle_search(conn, sid, active=True)
    assert len(get_active_searches(conn)) == 1


def test_get_searches_for_chat():
    conn = _make_db()
    add_search(conn, chat_id=111, query="jazz")
    add_search(conn, chat_id=111, query="soul")
    add_search(conn, chat_id=222, query="rock")
    results = get_searches_for_chat(conn, 111)
    assert len(results) == 2
    queries = {r["query"] for r in results}
    assert queries == {"jazz", "soul"}


def test_add_search_custom_params():
    conn = _make_db()
    add_search(conn, chat_id=111, query="rare", min_deal_score=0.4, poll_minutes=15)
    searches = get_searches_for_chat(conn, 111)
    assert searches[0]["min_deal_score"] == 0.4
    assert searches[0]["poll_minutes"] == 15


# -- ebay_listings --

def test_upsert_and_match_listing():
    conn = _make_db()
    upsert_release(conn, 1001, "Miles Davis", "Kind of Blue", median_price=30.0)
    upsert_listing(conn, item_id="ebay-001", title="Miles Davis Kind of Blue LP", price=12.0)
    update_listing_match(conn, "ebay-001", match_release_id=1001,
                         match_method="fuzzy", match_score=0.92, deal_score=0.60)
    deals = get_unnotified_deals(conn, min_deal_score=0.25)
    assert len(deals) == 1
    assert deals[0]["item_id"] == "ebay-001"
    assert deals[0]["deal_score"] == 0.60
    assert deals[0]["match_method"] == "fuzzy"


def test_mark_notified_removes_from_deals():
    conn = _make_db()
    upsert_release(conn, 1, "Artist", "Title", median_price=20.0)
    upsert_listing(conn, item_id="ebay-002", title="Test LP", price=5.0)
    update_listing_match(conn, "ebay-002", match_release_id=1,
                         match_method="catalog_no", match_score=1.0, deal_score=0.50)
    assert len(get_unnotified_deals(conn, 0.25)) == 1
    mark_notified(conn, "ebay-002")
    assert len(get_unnotified_deals(conn, 0.25)) == 0


def test_unnotified_deals_respects_threshold():
    conn = _make_db()
    upsert_release(conn, 1, "Artist", "Title", median_price=20.0)
    upsert_listing(conn, item_id="ebay-003", title="Cheap LP", price=3.0)
    update_listing_match(conn, "ebay-003", match_release_id=1,
                         match_method="barcode", match_score=1.0, deal_score=0.20)
    assert get_unnotified_deals(conn, min_deal_score=0.25) == []
    assert len(get_unnotified_deals(conn, min_deal_score=0.15)) == 1


# -- alert_log --

def test_log_and_check_alert():
    conn = _make_db()
    log_alert(conn, chat_id=111, item_id="ebay-001", deal_score=0.55)
    assert was_alerted(conn, 111, "ebay-001") is True


def test_was_alerted_different_chat():
    conn = _make_db()
    log_alert(conn, chat_id=111, item_id="ebay-001", deal_score=0.55)
    assert was_alerted(conn, 222, "ebay-001") is False


def test_was_alerted_no_record():
    conn = _make_db()
    assert was_alerted(conn, 111, "ebay-999") is False
