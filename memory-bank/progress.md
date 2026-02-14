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
| 4 | Combined fetch-and-cache function | |
| 5 | Batch refresh for stale releases | |
| 6 | Discogs search for seeding | |
| 7 | Lint + full test pass | |

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
- Plan 2 Step 1: `discogs.py` — `DiscogsClient` class with `httpx.AsyncClient` (base_url, auth header, user-agent, 30s timeout), async context manager. Installed httpx. 5 tests in `test_discogs.py`. All 43 tests pass, ruff clean.
- Plan 2 Step 2: `discogs.py` — Added `get_release(release_id)` async method: rate-limits, GETs `/releases/{id}`, returns None on 404, raises `DiscogsAPIError` on other errors. `_parse_release()` helper extracts `release_id`, `artist` (strips trailing ` (N)` disambiguation), `title`, `catalog_no`, `barcode`, `format`. 8 tests in `test_discogs_release.py` (parse full/stripped/missing/no-barcode, HTTP 200/404/429/500). All 51 tests pass, ruff clean.
- Plan 2 Step 3: `discogs.py` — Added `get_price_stats(release_id)` async method: uses `/marketplace/price_suggestions/{id}` (requires seller settings configured). Returns `{"median_price": float, "low_price": float}` from VG+ and Good conditions, or None if 404/no VG+ data. 4 tests in `test_discogs_price.py` (200 full, 200 missing VG+, 404, 500). All 55 tests pass, ruff clean.
