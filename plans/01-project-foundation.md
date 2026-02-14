# Plan 1: Project Foundation

**Goal:** Create the project skeleton, configuration loader, database layer, and rate limiter utility.

**Depends on:** Nothing (start here)
**Produces:** A runnable package (`python -m vinyl_detective`) that initializes the DB and exits cleanly.

---

## Step 1: Create the package structure

Create these files (all empty or minimal):

```
vinyl_detective/
    __init__.py
    __main__.py
    config.py
    db.py
    rate_limiter.py
```

Also create:
- `requirements.txt` with: `httpx>=0.27`, `rapidfuzz>=3.10`, `python-telegram-bot>=21.0`
- `requirements-dev.txt` with: `python-dotenv`, `pytest`, `pytest-asyncio`, `ruff`
- `.env.example` with placeholder keys: `DISCOGS_TOKEN`, `EBAY_APP_ID`, `EBAY_CERT_ID`, `TELEGRAM_TOKEN`

**Test:** Run `python -m vinyl_detective` from the repo root. It should import without errors (can exit immediately or print "starting").

---

## Step 2: Implement `config.py`

Create a module that loads configuration from environment variables.

- Define a dataclass or plain class `Config` with fields: `discogs_token: str`, `ebay_app_id: str`, `ebay_cert_id: str`, `telegram_token: str`, `db_path: str` (default `"vinyl_detective.db"`), `ebay_poll_minutes: int` (default `30`), `discogs_refresh_days: int` (default `7`).
- Write a function `load_config() -> Config` that reads from `os.environ`. Use `python-dotenv`'s `load_dotenv()` at the top so `.env` files work in dev.
- If any required key is missing, raise `ValueError` with a clear message naming the missing key(s).

**Test:** Write `tests/test_config.py`:
1. Set all 4 required env vars in the test (use `monkeypatch`), call `load_config()`, assert all fields populated.
2. Unset `DISCOGS_TOKEN`, call `load_config()`, assert `ValueError` is raised and the message contains `"DISCOGS_TOKEN"`.

---

## Step 3: Implement `db.py` -- schema initialization

Create the database initialization layer.

- Write a function `init_db(db_path: str) -> sqlite3.Connection` that:
  1. Opens a SQLite connection with `check_same_thread=False`.
  2. Executes the PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `cache_size=-64000`.
  3. Creates all 4 tables (`discogs_releases`, `ebay_listings`, `saved_searches`, `alert_log`) using `CREATE TABLE IF NOT EXISTS`.
  4. Creates the FTS5 virtual table `releases_fts` with `content=discogs_releases, content_rowid=release_id`.
  5. Creates all 4 indexes using `CREATE INDEX IF NOT EXISTS`.
  6. Returns the connection.
- Use the exact schema from `memory-bank/tech-stack.md` (lines 91-146).

**Test:** Write `tests/test_db.py`:
1. Call `init_db(":memory:")`.
2. Query `sqlite_master` and assert all 4 tables exist.
3. Assert `releases_fts` virtual table exists.
4. Assert all 4 indexes exist.
5. Assert `PRAGMA journal_mode` returns `wal` (note: for `:memory:` it returns `memory`, so use a temp file for this assertion).

---

## Step 4: Implement `db.py` -- CRUD helpers for `discogs_releases`

Add functions to `db.py` for the Discogs releases table:

- `upsert_release(conn, release_id, artist, title, catalog_no, barcode, format_, median_price, low_price)` -- INSERT OR REPLACE. Also update the FTS5 index (DELETE old row from FTS, INSERT new row).
- `get_release(conn, release_id) -> dict | None` -- fetch one release by ID, return as dict.
- `get_stale_releases(conn, max_age_days: int) -> list[dict]` -- return releases where `updated_at` is older than `max_age_days` days ago (compare against `int(time.time())`), or `updated_at IS NULL`.
- `lookup_by_catalog(conn, normalized_catalog_no: str) -> dict | None` -- exact match on `catalog_no` column.
- `lookup_by_barcode(conn, barcode: str) -> dict | None` -- exact match on `barcode` column.

**Test:** Write `tests/test_db_releases.py`:
1. Init an in-memory DB. Upsert a release with known values. Call `get_release()` and assert all fields match.
2. Upsert the same `release_id` with a new `median_price`. Call `get_release()` and assert price is updated.
3. Upsert a release with `updated_at` = 30 days ago. Call `get_stale_releases(max_age_days=7)` and assert it appears.
4. Upsert a release with `catalog_no="BLP-4003"`. Call `lookup_by_catalog("BLP4003")` -- this should NOT match (no normalization in DB layer). Caller normalizes before calling. Call `lookup_by_catalog("BLP-4003")` and assert it matches.
5. Upsert a release with `barcode="123456789"`. Call `lookup_by_barcode("123456789")` and assert match.

---

## Step 5: Implement `db.py` -- CRUD helpers for other tables

Add functions:

**`saved_searches` table:**
- `add_search(conn, chat_id, query, min_deal_score=0.25, poll_minutes=30) -> int` -- INSERT, return the new row ID.
- `get_active_searches(conn) -> list[dict]` -- return all rows where `active=1`.
- `get_searches_for_chat(conn, chat_id) -> list[dict]` -- return all rows for a given `chat_id`.
- `toggle_search(conn, search_id, active: bool)` -- UPDATE `active` field.

**`ebay_listings` table:**
- `upsert_listing(conn, item_id, title, price, shipping, condition, seller_rating, first_seen)` -- INSERT OR REPLACE.
- `update_listing_match(conn, item_id, match_release_id, match_method, match_score, deal_score)` -- UPDATE match fields.
- `get_unnotified_deals(conn, min_deal_score: float) -> list[dict]` -- return listings where `deal_score >= min_deal_score` AND `notified_at IS NULL`.
- `mark_notified(conn, item_id)` -- set `notified_at` to current timestamp.

**`alert_log` table:**
- `log_alert(conn, chat_id, item_id, deal_score)` -- INSERT with `sent_at = int(time.time())`.
- `was_alerted(conn, chat_id, item_id) -> bool` -- check if an alert was already sent.

**Test:** Write `tests/test_db_crud.py`:
1. Add a search, retrieve active searches, assert it appears.
2. Toggle search inactive, retrieve active searches, assert it's gone.
3. Upsert a listing, update its match, retrieve unnotified deals with matching score, assert it appears.
4. Mark it notified, retrieve unnotified deals again, assert it's gone.
5. Log an alert, call `was_alerted()` with same chat_id/item_id, assert True. Call with different chat_id, assert False.

---

## Step 6: Implement `db.py` -- FTS5 search helper

Add a function:

- `fts5_search(conn, query: str, limit: int = 50) -> list[dict]` -- query the `releases_fts` table. Tokenize the input query (split on whitespace, strip punctuation), join with spaces for FTS5 implicit AND. Return matching rows joined back to `discogs_releases` (need `release_id`, `artist`, `title`, `catalog_no`, `median_price`). Order by FTS5 rank. Limit results.

**Test:** Write `tests/test_db_fts.py`:
1. Init DB. Upsert 3 releases: ("Miles Davis", "Kind of Blue", ...), ("John Coltrane", "Blue Train", ...), ("Thelonious Monk", "Brilliant Corners", ...).
2. Call `fts5_search(conn, "Miles Davis Blue")`. Assert "Kind of Blue" is in results.
3. Call `fts5_search(conn, "Coltrane Train")`. Assert "Blue Train" is in results.
4. Call `fts5_search(conn, "xyznonexistent")`. Assert empty list returned.

---

## Step 7: Implement `rate_limiter.py`

Create a class `RateLimiter`:

- Constructor takes `calls_per_minute: int`.
- Stores `interval = 60.0 / calls_per_minute`, an `asyncio.Lock`, and `last_call: float = 0.0`.
- Has an async method `wait()` that acquires the lock, calculates time since last call, sleeps if needed, then updates `last_call`.
- Use `asyncio.get_event_loop().time()` (or `time.monotonic()`) for timing.

**Test:** Write `tests/test_rate_limiter.py`:
1. Create a `RateLimiter(calls_per_minute=60)` (1 call/sec).
2. Call `wait()` twice in rapid succession. Measure elapsed time. Assert the second call was delayed by ~1 second (tolerance +/- 0.1s).
3. Create a `RateLimiter(calls_per_minute=600)` (10 calls/sec). Call `wait()` 5 times. Assert total elapsed < 1 second.

---

## Step 8: Wire up `__main__.py` with a basic startup

Make `vinyl_detective/__main__.py` do the following:

1. Import and call `load_config()` to get config.
2. Import and call `init_db(config.db_path)` to get a DB connection.
3. Print/log "Vinyl Detective started. DB initialized at {config.db_path}".
4. Close the connection and exit (the full async loop comes in Plan 6).

**Test:**
1. Create a `.env` file with dummy values for all 4 required keys.
2. Run `python -m vinyl_detective`. Assert it prints the startup message and exits with code 0.
3. Assert the SQLite file was created at the expected path.
4. Clean up the created DB file after the test.

---

## Step 9: Lint and formatting check

- Run `ruff check vinyl_detective/ tests/` and fix any issues.
- Run `pytest tests/ -v` and confirm all tests pass.

**Test:** Both commands exit with code 0.
