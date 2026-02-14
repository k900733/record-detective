# Plan 2: Discogs API Client

**Goal:** Build the Discogs API client that fetches release info and median sale prices, then caches them in SQLite.

**Depends on:** Plan 1 (config, db, rate_limiter)
**Produces:** A `discogs.py` module that can populate and refresh the price database.

---

## Step 1: Create `vinyl_detective/discogs.py` with client class

Create a class `DiscogsClient`:

- Constructor takes `token: str` and `rate_limiter: RateLimiter`.
- Creates an `httpx.AsyncClient` with:
  - `base_url="https://api.discogs.com"`
  - `headers={"Authorization": f"Discogs token={token}", "User-Agent": "VinylDetective/1.0"}`
  - `timeout=httpx.Timeout(30.0)`
- Has an async context manager (`__aenter__`/`__aexit__`) that opens/closes the httpx client.

**Test:** Write `tests/test_discogs.py`:
1. Instantiate `DiscogsClient` with a dummy token and a `RateLimiter(60)`.
2. Assert the client's httpx headers contain the Authorization header.
3. Assert the User-Agent header is set.

---

## Step 2: Implement release lookup

Add an async method `get_release(self, release_id: int) -> dict | None`:

1. Call `self.rate_limiter.wait()`.
2. GET `/releases/{release_id}`.
3. If response status is 404, return `None`.
4. If response status is not 200, raise an exception with status code and body.
5. Parse JSON. Extract and return a dict with keys: `release_id`, `artist` (from `artists[0].name`, strip trailing " (N)" numbering), `title`, `catalog_no` (from `labels[0].catno` if present), `barcode` (from `identifiers` list, find type "Barcode"), `format` (from `formats[0].name`).

**Test:** Write `tests/test_discogs_release.py` using `httpx`'s mock transport or `pytest-httpx` (or manual monkeypatch):
1. Mock a 200 response with a sample Discogs release JSON (include `artists`, `title`, `labels`, `identifiers`, `formats` fields). Call `get_release()`. Assert returned dict has correct `artist`, `title`, `catalog_no`, `barcode`, `format`.
2. Mock a 404 response. Call `get_release()`. Assert returns `None`.
3. Mock a 429 response. Call `get_release()`. Assert an exception is raised.

---

## Step 3: Implement price statistics lookup

Add an async method `get_price_stats(self, release_id: int) -> dict | None`:

1. Call `self.rate_limiter.wait()`.
2. GET `/marketplace/price_suggestions/{release_id}`.
3. If 404, return `None`.
4. Parse JSON. The response has keys like `"Mint (M)"`, `"Very Good Plus (VG+)"`, etc., each with `value` and `currency`.
5. Extract `median_price` as the `"Very Good Plus (VG+)"` value (this is the most common trading condition). Extract `low_price` as the `"Good (G)"` value. Both in USD.
6. Return `{"median_price": float, "low_price": float}`.
7. If the condition keys don't exist (no sales data), return `None`.

**Note on API:** Verify the actual Discogs API endpoint. An alternative is `/marketplace/stats/{release_id}` which returns `lowest_price` and `num_for_sale`. Check the Discogs API docs and use whichever endpoint provides median/market price info. If `price_suggestions` requires seller auth, fall back to `community.rating` data from the release endpoint combined with marketplace stats.

**Test:** Write `tests/test_discogs_price.py`:
1. Mock a 200 response with sample price suggestion JSON. Call `get_price_stats()`. Assert `median_price` and `low_price` are correct floats.
2. Mock a response where the condition keys are missing. Assert returns `None`.
3. Mock a 404. Assert returns `None`.

---

## Step 4: Implement combined fetch-and-cache function

Add a standalone async function `fetch_and_cache_release(client: DiscogsClient, db: sqlite3.Connection, release_id: int) -> bool`:

1. Call `client.get_release(release_id)`. If `None`, return `False`.
2. Call `client.get_price_stats(release_id)`. If `None`, set `median_price=None`, `low_price=None`.
3. Call `db.upsert_release(...)` with all the combined data. Set `updated_at = int(time.time())`.
4. Return `True`.

**Test:** Write `tests/test_discogs_cache.py`:
1. Mock both API calls to return valid data. Call `fetch_and_cache_release()`. Assert returns `True`. Query the DB and assert the release row exists with correct values.
2. Mock `get_release()` to return `None`. Call the function. Assert returns `False`. Assert no row in DB.

---

## Step 5: Implement batch refresh for stale releases

Add an async function `refresh_stale_prices(client: DiscogsClient, db: sqlite3.Connection, max_age_days: int = 7) -> int`:

1. Call `db.get_stale_releases(max_age_days)` to get releases needing refresh.
2. For each stale release, call `client.get_price_stats(release.release_id)`.
3. If price data returned, update the release's `median_price`, `low_price`, and `updated_at` in the DB.
4. Return the count of successfully refreshed releases.
5. Handle errors per-release (log and continue, don't abort the batch).

**Test:** Write `tests/test_discogs_refresh.py`:
1. Init DB. Insert 2 releases: one with `updated_at` = 30 days ago, one with `updated_at` = 1 day ago.
2. Mock `get_price_stats()` to return new prices.
3. Call `refresh_stale_prices(max_age_days=7)`. Assert returns `1` (only the stale one).
4. Query DB. Assert the stale release has updated prices. Assert the fresh release is unchanged.

---

## Step 6: Implement Discogs search for seeding

Add an async method `search_releases(self, query: str, format_: str | None = None, per_page: int = 50) -> list[dict]`:

1. Call `self.rate_limiter.wait()`.
2. GET `/database/search` with params: `q=query`, `type=release`, `per_page=per_page`. If `format_` provided, add `format=format_`.
3. Parse JSON. Extract `results` list. For each result, return a dict with `release_id` (from `id`), `title` (from `title`), `format` (from `format` list), `catalog_no` (from `catno`).
4. Return the list.

This is used for initial seeding -- search by genre/label, then fetch full details for each result.

**Test:** Write `tests/test_discogs_search.py`:
1. Mock a 200 response with a sample search results JSON (include `results` array with 2-3 items). Call `search_releases("blue note jazz")`. Assert returned list has correct length and fields.
2. Mock an empty `results` array. Assert returns empty list.

---

## Step 7: Lint and test

- Run `ruff check vinyl_detective/discogs.py tests/test_discogs*.py`.
- Run `pytest tests/test_discogs*.py -v`.

**Test:** All pass, zero lint errors.
