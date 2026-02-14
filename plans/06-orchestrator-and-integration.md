# Plan 6: Main Orchestrator & Integration

**Goal:** Wire everything together into the main async event loop with polling tasks, and run the full end-to-end pipeline.

**Depends on:** Plans 1-5 (all modules)
**Produces:** A fully functional `python -m vinyl_detective` that polls eBay, matches deals, and sends Telegram alerts.

---

## Step 1: Create `vinyl_detective/pipeline.py` with the scan-match-score pipeline

Create a function `async scan_and_score(ebay_client, db, search_query: str) -> list[Deal]`:

1. Call `ebay_client.search_listings(search_query)` to get raw eBay listings.
2. For each listing:
   a. Extract UPC if available (call `ebay_client.get_item(item_id)` for enrichment, then `extract_upc()`). Note: to save API calls, only enrich if no catalog number found in title.
   b. Call `matcher.match_listing(db, listing["title"], upc=extracted_upc)`.
   c. If no match, skip.
   d. Call `scorer.score_deal(listing, match_result)`.
   e. If deal is `None` (overpriced or no price data), skip.
   f. Call `db.upsert_listing(...)` with the listing data.
   g. Call `db.update_listing_match(...)` with match and score data.
   h. Append to results.
3. Return the list of `Deal` objects.

**Test:** Write `tests/test_pipeline.py`:
1. Mock `ebay_client.search_listings` to return 3 listings. Mock `matcher.match_listing` to match 2 of them. Mock `scorer.score_deal` to score 1 as a deal. Call `scan_and_score()`. Assert returns 1 deal.
2. Mock `search_listings` to return an empty list. Assert returns empty list.
3. Mock all 3 listings matching and scoring. Assert returns 3 deals and all are in the DB.

---

## Step 2: Implement the eBay polling loop

Add to `pipeline.py` (or a new `vinyl_detective/loops.py`):

```
async def poll_ebay_loop(ebay_client, db, bot, config):
```

1. Loop forever:
   a. Call `db.get_active_searches()`.
   b. For each search, call `scan_and_score(ebay_client, db, search.query)`.
   c. Filter deals by the search's `min_deal_score`.
   d. Call `send_deal_alerts(bot, db, filtered_deals, config.affiliate_campaign_id)`.
   e. Log the count of deals found per search.
   f. Sleep for `config.ebay_poll_minutes * 60` seconds.
2. Wrap the loop body in try/except to log errors and continue (don't crash the loop).

**Test:** Write `tests/test_poll_loop.py`:
1. Mock all dependencies. Set `config.ebay_poll_minutes = 0` (don't actually sleep). Insert one active search.
2. Run the loop with a mechanism to break after 1 iteration (e.g., mock `asyncio.sleep` to raise `StopIteration` or use `asyncio.wait_for` with a short timeout).
3. Assert `scan_and_score` was called once with the search query.
4. Assert `send_deal_alerts` was called.

---

## Step 3: Implement the Discogs refresh loop

Add:

```
async def refresh_discogs_loop(discogs_client, db, config):
```

1. Loop forever:
   a. Call `refresh_stale_prices(discogs_client, db, max_age_days=config.discogs_refresh_days)`.
   b. Log how many releases were refreshed.
   c. Sleep for 24 hours (daily check).
2. Wrap in try/except for resilience.

**Test:** Write `tests/test_refresh_loop.py`:
1. Mock `refresh_stale_prices` to return 5. Run the loop for 1 iteration.
2. Assert `refresh_stale_prices` was called with the correct `max_age_days`.

---

## Step 4: Implement the cleanup loop

Add:

```
async def cleanup_stale_loop(db):
```

1. Loop forever:
   a. Delete `ebay_listings` older than 30 days (where `first_seen < now - 30 days`).
   b. Delete `alert_log` entries older than 90 days.
   c. Log counts.
   d. Sleep for 24 hours.

**Test:** Write `tests/test_cleanup.py`:
1. Insert listings with `first_seen` = 60 days ago and `first_seen` = 5 days ago.
2. Run cleanup once. Assert old listing is deleted, recent one remains.
3. Insert alert_log entries from 100 days ago and 10 days ago. Assert old one is deleted.

---

## Step 5: Wire up `__main__.py` with the full async orchestrator

Update `vinyl_detective/__main__.py`:

1. `load_config()`.
2. `init_db(config.db_path)`.
3. Create `DiscogsClient(config.discogs_token, discogs_limiter)`.
4. Create `EbayClient(config.ebay_app_id, config.ebay_cert_id, ebay_limiter)`.
5. Create the Telegram bot Application via `create_bot(config.telegram_token, db)`.
6. Set up logging (to stdout, INFO level).
7. Run `asyncio.gather()` with:
   - `bot.run_polling()` (Telegram long-polling -- note: `run_polling()` is a blocking method in python-telegram-bot v21. Use `bot.updater.start_polling()` and `bot.start()` instead, or run the bot's event loop integration properly with asyncio).
   - `poll_ebay_loop(ebay_client, db, bot.bot, config)`
   - `refresh_discogs_loop(discogs_client, db, config)`
   - `cleanup_stale_loop(db)`
8. Handle graceful shutdown on SIGINT/SIGTERM: cancel tasks, close clients, close DB.

**Important:** Research `python-telegram-bot` v21 async integration pattern. The `Application.run_polling()` method manages its own event loop. The correct approach may be to use `Application.initialize()`, `Application.start()`, `Application.updater.start_polling()` within an existing `asyncio.run()`, then `Application.stop()` on shutdown.

**Test:** Write `tests/test_main_integration.py`:
1. This is a smoke test. Mock all external API calls (Discogs, eBay, Telegram).
2. Set up env vars with test values. Call the main startup logic (not the infinite loops).
3. Assert: config loaded, DB initialized, all clients created without error.
4. Assert the DB file exists and has the correct schema.

---

## Step 6: Add graceful shutdown handling

In `__main__.py`:

1. Register signal handlers for `SIGINT` and `SIGTERM`.
2. On signal, set a shutdown event (`asyncio.Event`).
3. Modify all loops to check `shutdown_event.is_set()` instead of `while True`.
4. On shutdown: close httpx clients, close DB connection, log "Vinyl Detective stopped."

**Test:** Write `tests/test_shutdown.py`:
1. Start the main orchestrator in a background task.
2. Send `SIGINT` (or set the shutdown event directly).
3. Assert the task completes within 5 seconds.
4. Assert "stopped" appears in logs.

---

## Step 7: End-to-end integration test

Write `tests/test_e2e.py`:

1. Create an in-memory DB. Insert 3 Discogs releases with known prices.
2. Mock eBay search to return 5 listings, 2 of which match the Discogs releases and are underpriced.
3. Mock the Telegram bot's `send_message`.
4. Run the pipeline once (not the loop, just one iteration of scan_and_score + send_deal_alerts).
5. Assert:
   - 2 deals were scored.
   - 2 Telegram messages were sent (or fewer if same chat_id and dedup applied).
   - Both deals appear in `ebay_listings` table with correct `match_release_id` and `deal_score`.
   - Both appear in `alert_log`.
6. Run the pipeline again with the same data. Assert no new messages sent (dedup works).

---

## Step 8: Final lint, test, and manual smoke test

1. Run `ruff check vinyl_detective/ tests/`.
2. Run `pytest tests/ -v --tb=short`.
3. All tests pass.
4. Create a real `.env` with valid API keys (manual step for the developer).
5. Run `python -m vinyl_detective` manually. Verify:
   - Startup log appears.
   - Telegram bot responds to `/start`.
   - At least one eBay poll cycle completes and logs results.
   - Ctrl+C shuts down gracefully.

**Test:** Steps 1-3 are automated. Steps 4-5 are manual verification documented here for the developer.
