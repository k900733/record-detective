# Plan 3: eBay API Client

**Goal:** Build the eBay Browse API client that authenticates via OAuth2 and searches for music listings.

**Depends on:** Plan 1 (config, rate_limiter)
**Produces:** An `ebay.py` module that can search eBay and return parsed listing data.

---

## Step 1: Create `vinyl_detective/ebay.py` with OAuth2 token management

Create a class `EbayClient`:

- Constructor takes `app_id: str`, `cert_id: str`, and `rate_limiter: RateLimiter`.
- Stores `_access_token: str | None = None` and `_token_expires: float = 0.0`.
- Has an async context manager that opens/closes an `httpx.AsyncClient`.

Add a private async method `_ensure_token(self)`:

1. If `_access_token` is not None and `time.time() < _token_expires - 60` (60s buffer), return early.
2. Otherwise, POST to `https://api.ebay.com/identity/v1/oauth2/token` with:
   - `Content-Type: application/x-www-form-urlencoded`
   - Body: `grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope`
   - HTTP Basic auth with `app_id` as username and `cert_id` as password.
3. Parse response JSON. Store `access_token` and compute `_token_expires = time.time() + expires_in`.
4. If response is not 200, raise an exception.

**Test:** Write `tests/test_ebay_auth.py`:
1. Mock the token endpoint to return `{"access_token": "test_token", "expires_in": 7200}`. Create `EbayClient`, call `_ensure_token()`. Assert `_access_token == "test_token"`.
2. Call `_ensure_token()` again immediately. Assert the token endpoint was NOT called a second time (token is cached).
3. Set `_token_expires` to a past time. Call `_ensure_token()`. Assert the token endpoint WAS called again.

---

## Step 2: Implement listing search

Add an async method `search_listings(self, query: str, limit: int = 200) -> list[dict]`:

1. Call `_ensure_token()`.
2. Call `self.rate_limiter.wait()`.
3. GET `https://api.ebay.com/buy/browse/v1/item_summary/search` with:
   - Headers: `Authorization: Bearer {access_token}`, `X-EBAY-C-MARKETPLACE-ID: EBAY_US`
   - Params: `q=query`, `limit=limit`, `filter=buyingOptions:{FIXED_PRICE}` (skip auctions for V1), `category_ids=176985` (Records category) or make category configurable.
4. Parse JSON. Extract `itemSummaries` list (may be absent if no results -- return empty list).
5. For each item, extract and return a dict with: `item_id` (from `itemId`), `title`, `price` (from `price.value`, convert to float), `currency` (from `price.currency`), `condition` (from `condition`), `seller_rating` (from `seller.feedbackPercentage`), `image_url` (from `image.imageUrl`), `item_web_url` (from `itemWebUrl`), `shipping` (from `shippingOptions[0].shippingCost.value` if present, else 0).

**Test:** Write `tests/test_ebay_search.py`:
1. Mock the token endpoint and the search endpoint. Provide a sample response with 2 `itemSummaries`. Call `search_listings("blue note vinyl")`. Assert 2 results with correct fields.
2. Mock a response with no `itemSummaries` key. Assert returns empty list.
3. Mock a 401 response from search. Assert exception raised.

---

## Step 3: Implement affiliate link generation

Add a method `make_affiliate_url(self, item_web_url: str, campaign_id: str = "") -> str`:

1. If `campaign_id` is empty, return `item_web_url` unchanged.
2. Otherwise, append eBay Partner Network tracking params: `mkevt=1&mkcid=1&mkrid=711-53200-19255-0&campid={campaign_id}&toolid=10001` to the URL query string.
3. Use `urllib.parse.urlparse` and `urlencode` to build the URL cleanly.

**Test:** Write `tests/test_ebay_affiliate.py`:
1. Call `make_affiliate_url("https://www.ebay.com/itm/123", "5338")`. Assert the returned URL contains `campid=5338` and `mkevt=1`.
2. Call `make_affiliate_url("https://www.ebay.com/itm/123", "")`. Assert the URL is unchanged.
3. Call with a URL that already has query params. Assert existing params are preserved.

---

## Step 4: Implement listing detail fetch (optional enrichment)

Add an async method `get_item(self, item_id: str) -> dict | None`:

1. Call `_ensure_token()` and `rate_limiter.wait()`.
2. GET `https://api.ebay.com/buy/browse/v1/item/{item_id}`.
3. If 404, return `None`.
4. Parse JSON. Extract additional fields beyond what `search` provides: `description`, `localizedAspects` (contains UPC/barcode, catalog number, format details), `itemLocation`.
5. Return as dict.

This is used to enrich listings that need more data for matching (e.g., extracting UPC from item specifics).

**Test:** Write `tests/test_ebay_item.py`:
1. Mock a 200 response with sample item JSON including `localizedAspects` containing a UPC entry. Call `get_item()`. Assert the UPC is extractable from the response.
2. Mock a 404. Assert returns `None`.

---

## Step 5: Add UPC/catalog extraction helpers

Add standalone functions in `ebay.py`:

- `extract_upc(item_aspects: list[dict]) -> str | None` -- scan `localizedAspects` for an entry with `name` containing "UPC" or "EAN". Return the `value`.
- `extract_catalog_no_from_title(title: str) -> str | None` -- use regex to find common catalog number patterns in eBay titles (e.g., uppercase letters followed by dash and digits like `BLP-4003`, `MFSL 1-234`, `APP 3014`). Return the first match or `None`.
- `normalize_catalog(cat_no: str) -> str` -- strip spaces, dashes, underscores, dots. Uppercase. (e.g., `"BLP-4003"` -> `"BLP4003"`).

**Test:** Write `tests/test_ebay_extract.py`:
1. `extract_upc([{"name": "UPC", "value": "123456789"}])` returns `"123456789"`.
2. `extract_upc([{"name": "Color", "value": "Black"}])` returns `None`.
3. `extract_catalog_no_from_title("Blue Note BLP-4003 Art Blakey Vinyl LP")` returns `"BLP-4003"`.
4. `extract_catalog_no_from_title("rare jazz vinyl lot")` returns `None`.
5. `normalize_catalog("BLP-4003")` returns `"BLP4003"`.
6. `normalize_catalog("MFSL 1-234")` returns `"MFSL1234"`.

---

## Step 6: Lint and test

- Run `ruff check vinyl_detective/ebay.py tests/test_ebay*.py`.
- Run `pytest tests/test_ebay*.py -v`.

**Test:** All pass, zero lint errors.
