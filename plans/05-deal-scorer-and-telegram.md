# Plan 5: Deal Scorer & Telegram Alerts

**Goal:** Build the deal scoring logic and the Telegram bot that sends formatted deal alerts and handles user commands.

**Depends on:** Plan 1 (db, config), Plan 4 (MatchResult)
**Produces:** `scorer.py` and `telegram_bot.py` modules.

---

## Step 1: Create `vinyl_detective/scorer.py` with deal scoring

Create the module with:

- A dataclass `Deal` with fields: `item_id: str`, `ebay_title: str`, `ebay_price: float`, `shipping: float`, `condition: str | None`, `seller_rating: float | None`, `match: MatchResult`, `deal_score: float`, `priority: str` (one of `"high"`, `"medium"`, `"low"`), `item_web_url: str`.
- A function `score_deal(ebay_listing: dict, match: MatchResult) -> Deal | None`:
  1. If `match.median_price` is `None` or `<= 0`, return `None` (can't score without reference price).
  2. Compute `total_price = ebay_listing["price"] + ebay_listing.get("shipping", 0)`.
  3. Compute `deal_score = (match.median_price - total_price) / match.median_price`.
  4. If `deal_score < 0`, return `None` (overpriced, not a deal).
  5. Set `priority`: `"high"` if `deal_score >= 0.40`, `"medium"` if `>= 0.25`, else `"low"`.
  6. Return a `Deal` with all fields populated.

**Test:** Write `tests/test_scorer.py`:
1. Listing at $20, median $50, shipping $0. Assert `deal_score == 0.6`, `priority == "high"`.
2. Listing at $35, median $50, shipping $5. Total $40. Assert `deal_score == 0.2`, `priority == "low"`.
3. Listing at $30, median $50, shipping $0. Assert `deal_score == 0.4`, `priority == "high"`.
4. Listing at $60, median $50. Assert returns `None` (overpriced).
5. Match with `median_price=None`. Assert returns `None`.

---

## Step 2: Implement deal filtering

Add a function `filter_deals(deals: list[Deal], min_score: float = 0.25) -> list[Deal]`:

1. Return only deals where `deal_score >= min_score`.
2. Sort by `deal_score` descending (best deals first).

**Test:** Write `tests/test_scorer_filter.py`:
1. Create 3 deals with scores 0.6, 0.3, 0.1. Call `filter_deals(deals, min_score=0.25)`. Assert returns 2 deals, first has score 0.6.
2. Call `filter_deals(deals, min_score=0.5)`. Assert returns 1 deal.
3. Call with empty list. Assert returns empty list.

---

## Step 3: Create `vinyl_detective/telegram_bot.py` with alert formatter

Create the module with:

- A function `format_deal_message(deal: Deal, affiliate_url: str) -> str` that returns a formatted Telegram message (using MarkdownV2 or HTML parse mode). Include:
  - Artist and title (from `deal.match`)
  - eBay price and shipping
  - Discogs median price
  - Savings percentage (from `deal_score`)
  - Condition
  - Match confidence (method and score)
  - Priority indicator
  - Clickable affiliate link
- Use HTML parse mode (easier to escape than MarkdownV2).

The message should look like:
```
<b>DEAL FOUND</b> [HIGH]

<b>Art Blakey - Moanin'</b>
Price: $20.00 + $3.99 shipping
Discogs Median: $50.00
<b>You Save: 52%</b>

Condition: Very Good Plus (VG+)
Match: catalog_no (100%)

<a href="https://ebay.com/itm/123?affiliate_params">View on eBay</a>
```

**Test:** Write `tests/test_telegram_format.py`:
1. Create a sample `Deal` and call `format_deal_message()`. Assert the returned string contains the artist name, price, savings percentage, and the affiliate URL.
2. Assert HTML tags are present (`<b>`, `<a href=`).
3. Test with a deal that has `condition=None`. Assert no crash, condition line omitted or shows "N/A".

---

## Step 4: Implement the Telegram bot with command handlers

Set up the bot using `python-telegram-bot` v21+ async API:

- Create a function `create_bot(token: str, db: sqlite3.Connection) -> Application`:
  1. Build the Application using `ApplicationBuilder().token(token).build()`.
  2. Register command handlers:
     - `/start` -- send a welcome message explaining the bot.
     - `/add_search <query>` -- call `db.add_search(chat_id, query)`. Confirm to user.
     - `/my_searches` -- call `db.get_searches_for_chat(chat_id)`. List them with IDs and active status.
     - `/remove_search <id>` -- deactivate the search. Confirm.
     - `/set_threshold <value>` -- update the user's default `min_deal_score`. Store in `saved_searches` or a new user prefs mechanism (simplest: update all their searches).
     - `/help` -- list available commands.
  3. Return the Application.

**Test:** Write `tests/test_telegram_commands.py`:
1. This is harder to unit test. Use `python-telegram-bot`'s testing utilities or mock the `Update` and `Context` objects.
2. Mock an `/add_search blue note jazz` command. Assert `db.add_search()` was called with the correct query and chat_id.
3. Mock a `/my_searches` command. Pre-insert 2 searches for the chat_id. Assert the bot's reply text contains both search queries.
4. Mock `/remove_search 1`. Assert `db.toggle_search(1, False)` was called.

---

## Step 5: Implement the alert sending function

Add an async function `send_deal_alerts(bot: Bot, db: sqlite3.Connection, deals: list[Deal], affiliate_campaign_id: str = "")`:

1. For each deal in `deals`:
   a. Find which `saved_searches` would match this deal (compare search query against deal's listing info, or simpler: find all active searches whose `min_deal_score <= deal.deal_score`).
   b. For each matching search, check `db.was_alerted(search.chat_id, deal.item_id)`. If already alerted, skip.
   c. Generate the affiliate URL using `make_affiliate_url(deal.item_web_url, affiliate_campaign_id)`.
   d. Format the message using `format_deal_message(deal, affiliate_url)`.
   e. Send the message via `bot.send_message(chat_id=search.chat_id, text=message, parse_mode="HTML")`.
   f. Call `db.log_alert(search.chat_id, deal.item_id, deal.deal_score)`.
   g. Call `db.mark_notified(deal.item_id)`.
2. Handle send errors gracefully (log and continue).

**Test:** Write `tests/test_telegram_alerts.py`:
1. Mock the bot's `send_message`. Create a deal and a matching search in the DB. Call `send_deal_alerts()`. Assert `send_message` was called once with the correct chat_id and HTML content.
2. Pre-insert an alert_log entry for the same chat_id + item_id. Call `send_deal_alerts()` again. Assert `send_message` was NOT called (duplicate suppressed).
3. Create 2 searches for different chat_ids. Call with one deal. Assert `send_message` called twice with different chat_ids.

---

## Step 6: Lint and test

- Run `ruff check vinyl_detective/scorer.py vinyl_detective/telegram_bot.py tests/test_scorer*.py tests/test_telegram*.py`.
- Run `pytest tests/test_scorer*.py tests/test_telegram*.py -v`.

**Test:** All pass, zero lint errors.
