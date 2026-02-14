# Vinyl Detective - Implementation Progress

## Plan 1: Project Foundation

| Step | Description | Status |
|------|------------|--------|
| 1 | Package structure + requirements + .env.example | Done |
| 2 | config.py (env loader) | Done |
| 3 | db.py - schema init | Done |
| 4 | db.py - discogs_releases CRUD | Done |
| 5 | db.py - other tables CRUD | Done |
| 6 | db.py - FTS5 search | Done |
| 7 | rate_limiter.py | Done |
| 8 | __main__.py startup wiring | Done |
| 9 | Lint + full test pass | Done |

## Plan 2: Discogs API Client

| Step | Description | Status |
|------|------------|--------|
| 1 | DiscogsClient class with httpx + context manager | Done |
| 2 | Release lookup method | Done |
| 3 | Price statistics lookup | Done |
| 4 | Combined fetch-and-cache function | Done |
| 5 | Batch refresh for stale releases | Done |
| 6 | Discogs search for seeding | Done |
| 7 | Lint + full test pass | Done |

## Plan 3: eBay API Client

| Step | Description | Status |
|------|------------|--------|
| 1 | EbayClient class with OAuth2 token management | Done |
| 2 | Listing search method | Done |
| 3 | Affiliate link generation | Done |
| 4 | Listing detail fetch | Done |
| 5 | UPC/catalog extraction helpers | Done |
| 6 | Lint + full test pass | Done |

## Plan 4: Matching Engine

| Step | Description | Status |
|------|------------|--------|
| 1 | MatchResult dataclass + FUZZY_SCORE_CUTOFF constant | Done |
| 2 | Tier 1 — catalog number matching | Done |
| 3 | Tier 2 — barcode/UPC matching | Done |
| 4 | Tier 3 — fuzzy artist+title matching | Done |
| 5 | Unified match_listing() function | Done |
| 6 | Lint + full test pass | |

## Plan 5: Deal Scorer & Telegram Alerts

| Step | Description | Status |
|------|------------|--------|
| 1 | scorer.py — Deal dataclass + score_deal() | Done |
| 2 | Deal filtering function | Done |
| 3 | telegram_bot.py — alert formatter | Done |
| 4 | Telegram bot command handlers | Done |
| 5 | Alert sending function | Done |
| 6 | Lint + full test pass | Done |

## Plan 6: Main Orchestrator & Integration

| Step | Description | Status |
|------|------------|--------|
| 1 | pipeline.py — scan_and_score() | Done |
| 2 | eBay polling loop | Done |
| 3 | Discogs refresh loop | |
| 4 | Cleanup loop | |
| 5 | __main__.py full async orchestrator | |
| 6 | Graceful shutdown handling | |
| 7 | End-to-end integration test | |
| 8 | Final lint, test, smoke test | |

## Notes

- Using python3.12 (`/usr/bin/python3.12`)
- venv created at `./venv` with python-dotenv, pytest, ruff installed
- Step 2: `config.py` — frozen dataclass `Config` + `load_config()` with dotenv support, missing-key validation. 4 tests passing.
- Step 3: `db.py` — `init_db(db_path)` opens SQLite with WAL/NORMAL/FK/cache PRAGMAs, creates 4 tables + FTS5 virtual table + 4 indexes per tech-stack schema. `row_factory=sqlite3.Row` set. 5 tests passing (tables, FTS5, indexes, WAL mode, idempotency).
- Step 4: `db.py` — Added 5 CRUD functions: `upsert_release` (INSERT OR REPLACE + FTS5 sync), `get_release`, `get_stale_releases` (NULL or old `updated_at`), `lookup_by_catalog`, `lookup_by_barcode`. 7 tests passing in `test_db_releases.py`. All 16 tests pass.
- Step 5: `db.py` — Added 10 CRUD functions for remaining tables: `saved_searches` (add_search, get_active_searches, get_searches_for_chat, toggle_search), `ebay_listings` (upsert_listing, update_listing_match, get_unnotified_deals, mark_notified), `alert_log` (log_alert, was_alerted). 11 tests in `test_db_crud.py`. All 27 tests pass, ruff clean.
- Step 6: `db.py` — Added `fts5_search(conn, query, limit=50)` function: strips punctuation, tokenizes query for FTS5 implicit AND, joins `releases_fts` back to `discogs_releases`, orders by rank. 5 tests in `test_db_fts.py`. All 32 tests pass, ruff clean.
- Step 7: `rate_limiter.py` — `RateLimiter` class with `calls_per_minute` constructor, `interval`-based delay, `asyncio.Lock` for concurrency safety, `time.monotonic()` for timing. Async `wait()` method sleeps the remaining interval if called too soon. 3 tests in `test_rate_limiter.py` (delay enforcement, high-rate throughput, no-delay-after-interval). Installed `pytest-asyncio`. All 35 tests pass, ruff clean.
- Step 8: `__main__.py` — Calls `load_config()` then `init_db(config.db_path)`, prints startup message, closes connection and exits. 3 tests in `test_main.py` (subprocess: prints message + exit 0, creates DB file, fails without env vars). All 38 tests pass.
- Step 9: `ruff check` — all checks passed. `pytest tests/ -v` — all 38 tests pass (1.76s). Plan 1 complete.
- Plan 5 Step 1: `scorer.py` — `Deal` frozen dataclass (item_id, ebay_title, ebay_price, shipping, condition, seller_rating, match, deal_score, priority, item_web_url) + `score_deal(ebay_listing, match)` function: returns None if no median price or overpriced, computes `(median - total) / median`, assigns priority (high >= 0.40, medium >= 0.25, else low). 5 tests in `test_scorer.py`. All pass, ruff clean.
- Plan 2 Step 1: `discogs.py` — `DiscogsClient` class with `httpx.AsyncClient` (base_url, auth header, user-agent, 30s timeout), async context manager. Installed httpx. 5 tests in `test_discogs.py`. All 43 tests pass, ruff clean.
- Plan 2 Step 2: `discogs.py` — Added `get_release(release_id)` async method: rate-limits, GETs `/releases/{id}`, returns None on 404, raises `DiscogsAPIError` on other errors. `_parse_release()` helper extracts `release_id`, `artist` (strips trailing ` (N)` disambiguation), `title`, `catalog_no`, `barcode`, `format`. 8 tests in `test_discogs_release.py` (parse full/stripped/missing/no-barcode, HTTP 200/404/429/500). All 51 tests pass, ruff clean.
- Plan 2 Step 3: `discogs.py` — Added `get_price_stats(release_id)` async method: uses `/marketplace/price_suggestions/{id}` (requires seller settings configured). Returns `{"median_price": float, "low_price": float}` from VG+ and Good conditions, or None if 404/no VG+ data. 4 tests in `test_discogs_price.py` (200 full, 200 missing VG+, 404, 500). All 55 tests pass, ruff clean.
- Plan 2 Step 4: `discogs.py` — Added `fetch_and_cache_release(client, conn, release_id)` async function: calls `get_release()` (returns False if not found), then `get_price_stats()` (None-safe), then `upsert_release()` with combined data. Lazy-imports `db.upsert_release` to avoid circular deps. 3 tests in `test_discogs_cache.py` (success with prices, 404 release, success without prices). All 58 tests pass (3 pre-existing failures in config/main), ruff clean.
- Plan 2 Step 5: `discogs.py` — Added `refresh_stale_prices(client, conn, max_age_days=7)` async function: queries stale releases via `get_stale_releases()`, re-fetches prices via `get_price_stats()`, updates DB via `upsert_release()`. Per-release error handling (catches exceptions and continues). Returns count of successfully refreshed releases. 4 tests in `test_discogs_refresh.py` (stale-only refresh, skip on no prices, continue on error, refresh all with age=0). All 62 tests pass (same 3 pre-existing failures), ruff clean.
- Plan 2 Step 6: `discogs.py` — Added `search_releases(query, format_=None, per_page=50)` async method on `DiscogsClient`: rate-limits, GETs `/database/search` with params (q, type=release, per_page, optional format), raises `DiscogsAPIError` on non-200. Parses `results` list into dicts with `release_id`, `title`, `format`, `catalog_no`. 4 tests in `test_discogs_search.py` (200 with 3 results, empty results, format param passthrough, 500 error). All 66 tests pass (same 3 pre-existing failures), ruff clean.
- Plan 2 Step 7: `ruff check` on `discogs.py` + all test files — all checks passed. `pytest tests/test_discogs*.py -v` — 28/28 passed (1.19s). Full suite: 63 passed, 3 pre-existing failures unchanged. **Plan 2 complete.**
- Plan 3 Step 1: `ebay.py` — `EbayClient` class with `httpx.AsyncClient` (base_url `api.ebay.com`, user-agent, 30s timeout), async context manager, `_ensure_token()` OAuth2 client-credentials flow (POST to `/identity/v1/oauth2/token` with Basic auth, 60s expiry buffer). `EbayAPIError` exception class. 4 tests in `test_ebay_auth.py` (first-call fetch, cached second call, refresh after expiry, 401 error). All 4 pass, ruff clean.
- Plan 3 Step 2: `ebay.py` — Added `search_listings(query, limit=200)` async method: ensures token, rate-limits, GETs `/buy/browse/v1/item_summary/search` with Bearer auth, `EBAY_US` marketplace, `FIXED_PRICE` filter, Records category `176985`. Parses `itemSummaries` into dicts with `item_id`, `title`, `price`, `currency`, `condition`, `seller_rating`, `image_url`, `item_web_url`, `shipping`. 3 tests in `test_ebay_search.py` (2-item parse, empty results, 401 error). All 7 eBay tests pass, ruff clean.
- Plan 3 Step 3: `ebay.py` — Added `make_affiliate_url(item_web_url, campaign_id)` method on `EbayClient`: returns URL unchanged if `campaign_id` is empty, otherwise appends eBay Partner Network params (`mkevt`, `mkcid`, `mkrid`, `campid`, `toolid`) via `urllib.parse`. Preserves existing query params. 3 tests in `test_ebay_affiliate.py` (full params, empty campaign, existing params preserved). All 10 eBay tests pass, ruff clean.
- Plan 3 Step 4: `ebay.py` — Added `get_item(item_id)` async method: ensures token, rate-limits, GETs `/buy/browse/v1/item/{item_id}`, returns `None` on 404, raises `EbayAPIError` on other errors. Parses response into dict with `item_id`, `title`, `description`, `localized_aspects`, `item_location`, `price`, `currency`, `condition`, `item_web_url`. 3 tests in `test_ebay_item.py` (200 with UPC in aspects, 404, 500 error). All 13 eBay tests pass, ruff clean.
- Plan 3 Step 5: `ebay.py` — Added 3 standalone extraction helpers: `extract_upc(item_aspects)` scans `localizedAspects` for UPC/EAN entries; `extract_catalog_no_from_title(title)` uses regex (`_CATALOG_RE`) to find catalog patterns like `BLP-4003`, `MFSL 1-234`, `APP 3014`; `normalize_catalog(cat_no)` strips spaces/dashes/underscores/dots and uppercases. 11 tests in `test_ebay_extract.py`. All 24 eBay tests pass, ruff clean.
- Plan 3 Step 6: `ruff check` on `ebay.py` + all test files — all checks passed. `pytest tests/test_ebay*.py -v` — 24/24 passed (0.49s). **Plan 3 complete.**
- Plan 4 Step 1: `matcher.py` — Created `MatchResult` frozen dataclass (release_id, artist, title, median_price, method, score) and `FUZZY_SCORE_CUTOFF = 85` constant. 3 tests in `test_matcher.py` (field access, None price, cutoff value). All 3 pass, ruff clean.
- Plan 4 Step 2: `matcher.py` — Added `match_by_catalog(conn, ebay_title)`: extracts catalog number via `extract_catalog_no_from_title`, tries exact `lookup_by_catalog` first, then falls back to new `lookup_by_catalog_normalized` in `db.py` (SQL-side REPLACE+UPPER normalization). Returns `MatchResult(method="catalog_no", score=1.0)`. 4 tests in `test_matcher_catalog.py` (exact match, no catalog in title, normalized match, no DB match). All 97 pass (3 pre-existing failures), ruff clean.
- Plan 4 Step 3: `matcher.py` — Added `match_by_barcode(conn, upc)`: returns None for None/empty UPC, otherwise calls `db.lookup_by_barcode` and returns `MatchResult(method="barcode", score=1.0)`. 4 tests in `test_matcher_barcode.py` (match, no match in DB, None UPC, empty UPC). All 11 matcher tests pass, ruff clean.
- Plan 4 Step 4: `matcher.py` — Added `match_by_fuzzy(conn, ebay_title)`: uses `fts5_search` for candidate pre-filtering (limit=50), then `rapidfuzz.process.extractOne` with `token_sort_ratio` scorer and `FUZZY_SCORE_CUTOFF` (85). Returns `MatchResult(method="fuzzy", score=score/100.0)`. Installed rapidfuzz 3.14.3. 4 tests in `test_matcher_fuzzy.py` (Miles Davis match, unrelated no-match, Coltrane match, empty DB). All 15 matcher tests pass, ruff clean.
- Plan 4 Step 5: `matcher.py` — Added `match_listing(conn, ebay_title, upc=None)`: unified 3-tier cascade (catalog -> barcode -> fuzzy), returns first hit or None. 4 tests in `test_matcher_unified.py` (catalog wins over barcode, barcode fallback, fuzzy fallback, no match). All 19 matcher tests pass, ruff clean.
- Plan 5 Step 2: `scorer.py` — Added `filter_deals(deals, min_score=0.25)`: filters deals below threshold, sorts by `deal_score` descending. 3 tests in `test_scorer_filter.py` (default threshold keeps 2/3, high threshold keeps 1/3, empty list). All 8 scorer tests pass, ruff clean.
- Plan 5 Step 3: `telegram_bot.py` — Added `format_deal_message(deal, affiliate_url)`: HTML-formatted Telegram alert with priority tag, artist/title, eBay price+shipping, Discogs median, savings %, condition (omitted if None), match method+confidence, and clickable affiliate link. Uses `html.escape` for safety. 3 tests in `test_telegram_format.py` (key info present, HTML tags, condition=None handling). All 3 pass, ruff clean.
- Plan 5 Step 4: `telegram_bot.py` — Added `create_bot(token, conn)` returning a configured `Application` (python-telegram-bot v22.6). Six command handlers: `/start` (welcome), `/help` (command list), `/add_search` (creates saved search via `db.add_search`), `/my_searches` (lists searches with ID/status), `/remove_search` (deactivates via `db.toggle_search`), `/set_threshold` (updates `min_deal_score` for all user searches, validated 0-1). DB connection passed via `bot_data["db"]`. 11 tests in `test_telegram_commands.py` (each handler + usage errors + create_bot wiring). All 14 telegram tests pass, ruff clean.
- Plan 5 Step 5: `telegram_bot.py` — Added `send_deal_alerts(bot, conn, deals, affiliate_campaign_id="")` async function: fetches all active searches, filters by `min_deal_score <= deal.deal_score`, skips already-alerted `(chat_id, item_id)` pairs via `was_alerted()`, builds affiliate URL inline (eBay Partner Network params), formats via `format_deal_message()`, sends via `bot.send_message(parse_mode="HTML")`, logs via `log_alert()` and `mark_notified()`. Per-send error handling with logging. 7 tests in `test_telegram_alerts.py` (basic send, duplicate suppression, multi-chat, threshold filtering, affiliate URL, mark_notified, error continuation). All 29 scorer+telegram tests pass, ruff clean.
- Plan 5 Step 6: `ruff check` on `scorer.py`, `telegram_bot.py` + all test files — all checks passed. `pytest tests/test_scorer*.py tests/test_telegram*.py -v` — 29/29 passed (0.33s). **Plan 5 complete.**
- Plan 6 Step 1: `pipeline.py` — Created `scan_and_score(ebay_client, conn, search_query)` async function: searches eBay, extracts catalog number from title first (skips `get_item` if found), falls back to `get_item` + `extract_upc` for UPC enrichment, runs 3-tier `match_listing`, scores via `score_deal`, persists via `upsert_listing` + `update_listing_match`. 4 tests in `test_pipeline.py` (3-listings-1-deal, empty results, all-match-and-DB-stored, catalog-skips-get_item). All 4 pass, ruff clean. Full suite: 139 passed, 3 pre-existing failures unchanged.
- Plan 6 Step 2: `pipeline.py` — Added `poll_ebay_loop(ebay_client, conn, bot, config)` async function: infinite loop that fetches active searches via `get_active_searches()`, runs `scan_and_score()` per search, filters deals by `min_deal_score`, sends alerts via `send_deal_alerts()` with `config.affiliate_campaign_id`, sleeps `config.ebay_poll_minutes * 60` seconds. Try/except around loop body for resilience. Also added `affiliate_campaign_id` field to `Config` (optional, default empty). 4 tests in `test_poll_loop.py` (scan+alerts called, threshold filtering, multi-search scanning, error resilience). All 4 pass, ruff clean. Full suite: 143 passed, 3 pre-existing failures unchanged.
