# Plan 4: Matching Engine

**Goal:** Build the 3-tier matching engine that matches eBay listings to Discogs releases.

**Depends on:** Plan 1 (db layer with FTS5), Plan 3 (catalog/UPC extraction helpers)
**Produces:** A `matcher.py` module with a `match_listing()` function.

---

## Step 1: Create `vinyl_detective/matcher.py` with match result type

Create the module with:

- A dataclass `MatchResult` with fields: `release_id: int`, `artist: str`, `title: str`, `median_price: float | None`, `method: str` (one of `"catalog_no"`, `"barcode"`, `"fuzzy"`), `score: float` (0.0 to 1.0).
- Define a constant `FUZZY_SCORE_CUTOFF = 85` (minimum rapidfuzz score to accept a fuzzy match).

**Test:** Write `tests/test_matcher.py`:
1. Instantiate a `MatchResult` with sample values. Assert all fields are accessible and correctly typed.

---

## Step 2: Implement Tier 1 -- catalog number matching

Add a function `match_by_catalog(db, ebay_title: str) -> MatchResult | None`:

1. Call `extract_catalog_no_from_title(ebay_title)` (from `ebay.py`).
2. If no catalog number found, return `None`.
3. Call `normalize_catalog()` on the extracted number.
4. Query the DB: `SELECT * FROM discogs_releases WHERE catalog_no = ?` using the **un-normalized** catalog number first (since DB stores the original). If no match, try normalized: query all releases, normalize their `catalog_no` in Python, and compare. (Better approach: store a `catalog_no_normalized` column, or normalize at insert time. Decide which approach -- recommend normalizing at query time for V1 simplicity, but add a note that a normalized column is a future optimization.)
5. Actually, simplest V1 approach: normalize both sides. The DB `lookup_by_catalog` should accept a raw catalog_no. Add a helper `lookup_by_catalog_normalized(conn, catalog_no)` that does: `SELECT * FROM discogs_releases WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(catalog_no), ' ', ''), '-', ''), '_', ''), '.', '') = ?`. Pass the normalized version.
6. If match found, return `MatchResult(method="catalog_no", score=1.0, ...)`.

**Test:** Write `tests/test_matcher_catalog.py`:
1. Init DB. Insert a release with `catalog_no="BLP-4003"`.
2. Call `match_by_catalog(db, "Art Blakey Moanin Blue Note BLP-4003 Vinyl LP")`. Assert returns a `MatchResult` with `method="catalog_no"` and the correct `release_id`.
3. Call `match_by_catalog(db, "Art Blakey Moanin Vinyl LP")` (no catalog number in title). Assert returns `None`.
4. Insert a release with `catalog_no="MFSL 1-234"`. Call with title containing `"MFSL1-234"` (slightly different formatting). Assert it still matches after normalization.

---

## Step 3: Implement Tier 2 -- barcode/UPC matching

Add a function `match_by_barcode(db, upc: str | None) -> MatchResult | None`:

1. If `upc` is `None` or empty, return `None`.
2. Call `db.lookup_by_barcode(upc)`.
3. If match found, return `MatchResult(method="barcode", score=1.0, ...)`.

**Test:** Write `tests/test_matcher_barcode.py`:
1. Init DB. Insert a release with `barcode="074646868027"`.
2. Call `match_by_barcode(db, "074646868027")`. Assert returns a `MatchResult` with `method="barcode"`.
3. Call `match_by_barcode(db, "000000000000")`. Assert returns `None`.
4. Call `match_by_barcode(db, None)`. Assert returns `None`.

---

## Step 4: Implement Tier 3 -- fuzzy artist+title matching

Add a function `match_by_fuzzy(db, ebay_title: str) -> MatchResult | None`:

1. Call `db.fts5_search(ebay_title, limit=50)` to get candidate releases.
2. If no candidates, return `None`.
3. Build a list of candidate strings: `[f"{c['artist']} {c['title']}" for c in candidates]`.
4. Use `rapidfuzz.process.extractOne(ebay_title, candidate_strings, scorer=rapidfuzz.fuzz.token_sort_ratio, score_cutoff=FUZZY_SCORE_CUTOFF)`.
5. If no match above cutoff, return `None`.
6. Otherwise, return `MatchResult(method="fuzzy", score=result[1] / 100.0, ...)` using the matched candidate's data.

**Test:** Write `tests/test_matcher_fuzzy.py`:
1. Init DB. Insert releases: ("Miles Davis", "Kind of Blue"), ("John Coltrane", "A Love Supreme"), ("Thelonious Monk", "Brilliant Corners").
2. Call `match_by_fuzzy(db, "Miles Davis Kind Of Blue Original Press Vinyl")`. Assert returns a match with `artist="Miles Davis"`, `score >= 0.85`.
3. Call `match_by_fuzzy(db, "totally unrelated electronics product")`. Assert returns `None`.
4. Call `match_by_fuzzy(db, "Coltrane Love Supreme")`. Assert returns a match for "A Love Supreme".

---

## Step 5: Implement the unified `match_listing()` function

Add a function `match_listing(db, ebay_title: str, upc: str | None = None) -> MatchResult | None`:

1. Try Tier 1: `result = match_by_catalog(db, ebay_title)`. If result, return it.
2. Try Tier 2: `result = match_by_barcode(db, upc)`. If result, return it.
3. Try Tier 3: `result = match_by_fuzzy(db, ebay_title)`. If result, return it.
4. Return `None` (no match).

This ensures the highest-confidence method is always preferred.

**Test:** Write `tests/test_matcher_unified.py`:
1. Init DB. Insert a release with `catalog_no="BLP-4003"`, `barcode="074646868027"`, `artist="Art Blakey"`, `title="Moanin'"`.
2. Call `match_listing(db, "Art Blakey Moanin BLP-4003", upc="074646868027")`. Assert `method="catalog_no"` (Tier 1 wins).
3. Call `match_listing(db, "Art Blakey Moanin Vinyl", upc="074646868027")`. Assert `method="barcode"` (no catalog in title, Tier 2 wins).
4. Call `match_listing(db, "Art Blakey Moanin Original Pressing", upc=None)`. Assert `method="fuzzy"` (no catalog, no UPC, Tier 3).
5. Call `match_listing(db, "random electronics gadget", upc=None)`. Assert returns `None`.

---

## Step 6: Lint and test

- Run `ruff check vinyl_detective/matcher.py tests/test_matcher*.py`.
- Run `pytest tests/test_matcher*.py -v`.

**Test:** All pass, zero lint errors.
