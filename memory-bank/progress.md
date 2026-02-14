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
| 8 | __main__.py startup wiring | Pending |
| 9 | Lint + full test pass | Pending |

## Notes

- Using python3.12 (`/usr/bin/python3.12`)
- venv created at `./venv` with python-dotenv, pytest, ruff installed
- Step 2: `config.py` — frozen dataclass `Config` + `load_config()` with dotenv support, missing-key validation. 4 tests passing.
- Step 3: `db.py` — `init_db(db_path)` opens SQLite with WAL/NORMAL/FK/cache PRAGMAs, creates 4 tables + FTS5 virtual table + 4 indexes per tech-stack schema. `row_factory=sqlite3.Row` set. 5 tests passing (tables, FTS5, indexes, WAL mode, idempotency).
- Step 4: `db.py` — Added 5 CRUD functions: `upsert_release` (INSERT OR REPLACE + FTS5 sync), `get_release`, `get_stale_releases` (NULL or old `updated_at`), `lookup_by_catalog`, `lookup_by_barcode`. 7 tests passing in `test_db_releases.py`. All 16 tests pass.
- Step 5: `db.py` — Added 10 CRUD functions for remaining tables: `saved_searches` (add_search, get_active_searches, get_searches_for_chat, toggle_search), `ebay_listings` (upsert_listing, update_listing_match, get_unnotified_deals, mark_notified), `alert_log` (log_alert, was_alerted). 11 tests in `test_db_crud.py`. All 27 tests pass, ruff clean.
- Step 6: `db.py` — Added `fts5_search(conn, query, limit=50)` function: strips punctuation, tokenizes query for FTS5 implicit AND, joins `releases_fts` back to `discogs_releases`, orders by rank. 5 tests in `test_db_fts.py`. All 32 tests pass, ruff clean.
- Step 7: `rate_limiter.py` — `RateLimiter` class with `calls_per_minute` constructor, `interval`-based delay, `asyncio.Lock` for concurrency safety, `time.monotonic()` for timing. Async `wait()` method sleeps the remaining interval if called too soon. 3 tests in `test_rate_limiter.py` (delay enforcement, high-rate throughput, no-delay-after-interval). Installed `pytest-asyncio`. All 35 tests pass, ruff clean.
