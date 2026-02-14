"""SQLite database layer for Vinyl Detective."""

import sqlite3
import time

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS discogs_releases (
    release_id   INTEGER PRIMARY KEY,
    artist       TEXT NOT NULL,
    title        TEXT NOT NULL,
    catalog_no   TEXT,
    barcode      TEXT,
    format       TEXT,
    median_price REAL,
    low_price    REAL,
    updated_at   INTEGER
);

CREATE TABLE IF NOT EXISTS ebay_listings (
    item_id          TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    price            REAL NOT NULL,
    shipping         REAL DEFAULT 0,
    condition        TEXT,
    seller_rating    REAL,
    match_release_id INTEGER REFERENCES discogs_releases(release_id),
    match_method     TEXT,
    match_score      REAL,
    deal_score       REAL,
    notified_at      INTEGER,
    first_seen       INTEGER
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    query           TEXT NOT NULL,
    min_deal_score  REAL DEFAULT 0.25,
    poll_minutes    INTEGER DEFAULT 30,
    active          INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS alert_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    item_id    TEXT NOT NULL,
    sent_at    INTEGER NOT NULL,
    deal_score REAL
);

CREATE VIRTUAL TABLE IF NOT EXISTS releases_fts USING fts5(
    artist, title, catalog_no,
    content = discogs_releases,
    content_rowid = release_id
);

CREATE INDEX IF NOT EXISTS idx_releases_catalog ON discogs_releases(catalog_no);
CREATE INDEX IF NOT EXISTS idx_releases_barcode ON discogs_releases(barcode);
CREATE INDEX IF NOT EXISTS idx_listings_match   ON ebay_listings(match_release_id);
CREATE INDEX IF NOT EXISTS idx_searches_chat    ON saved_searches(chat_id);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection, apply PRAGMAs, create schema, return conn."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-64000")
    conn.executescript(_SCHEMA_SQL)
    return conn


def upsert_release(
    conn: sqlite3.Connection,
    release_id: int,
    artist: str,
    title: str,
    catalog_no: str | None = None,
    barcode: str | None = None,
    format_: str | None = None,
    median_price: float | None = None,
    low_price: float | None = None,
) -> None:
    """INSERT OR REPLACE a Discogs release and update the FTS5 index."""
    now = int(time.time())
    conn.execute(
        "DELETE FROM releases_fts WHERE rowid = ?", (release_id,)
    )
    conn.execute(
        """INSERT OR REPLACE INTO discogs_releases
           (release_id, artist, title, catalog_no, barcode, format,
            median_price, low_price, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (release_id, artist, title, catalog_no, barcode, format_,
         median_price, low_price, now),
    )
    conn.execute(
        """INSERT INTO releases_fts (rowid, artist, title, catalog_no)
           VALUES (?, ?, ?, ?)""",
        (release_id, artist, title, catalog_no),
    )
    conn.commit()


def get_release(conn: sqlite3.Connection, release_id: int) -> dict | None:
    """Fetch one release by ID, return as dict or None."""
    row = conn.execute(
        "SELECT * FROM discogs_releases WHERE release_id = ?", (release_id,)
    ).fetchone()
    return dict(row) if row else None


def get_stale_releases(
    conn: sqlite3.Connection, max_age_days: int
) -> list[dict]:
    """Return releases where updated_at is older than max_age_days or NULL."""
    cutoff = int(time.time()) - max_age_days * 86400
    rows = conn.execute(
        """SELECT * FROM discogs_releases
           WHERE updated_at IS NULL OR updated_at < ?""",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def lookup_by_catalog(
    conn: sqlite3.Connection, catalog_no: str
) -> dict | None:
    """Exact match on catalog_no column."""
    row = conn.execute(
        "SELECT * FROM discogs_releases WHERE catalog_no = ?", (catalog_no,)
    ).fetchone()
    return dict(row) if row else None


def lookup_by_barcode(
    conn: sqlite3.Connection, barcode: str
) -> dict | None:
    """Exact match on barcode column."""
    row = conn.execute(
        "SELECT * FROM discogs_releases WHERE barcode = ?", (barcode,)
    ).fetchone()
    return dict(row) if row else None


# -- saved_searches CRUD --

def add_search(
    conn: sqlite3.Connection,
    chat_id: int,
    query: str,
    min_deal_score: float = 0.25,
    poll_minutes: int = 30,
) -> int:
    """Insert a saved search, return new row ID."""
    cur = conn.execute(
        """INSERT INTO saved_searches (chat_id, query, min_deal_score, poll_minutes)
           VALUES (?, ?, ?, ?)""",
        (chat_id, query, min_deal_score, poll_minutes),
    )
    conn.commit()
    return cur.lastrowid


def get_active_searches(conn: sqlite3.Connection) -> list[dict]:
    """Return all saved searches where active=1."""
    rows = conn.execute(
        "SELECT * FROM saved_searches WHERE active = 1"
    ).fetchall()
    return [dict(r) for r in rows]


def get_searches_for_chat(
    conn: sqlite3.Connection, chat_id: int
) -> list[dict]:
    """Return all saved searches for a given chat_id."""
    rows = conn.execute(
        "SELECT * FROM saved_searches WHERE chat_id = ?", (chat_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def toggle_search(
    conn: sqlite3.Connection, search_id: int, active: bool
) -> None:
    """Set the active flag on a saved search."""
    conn.execute(
        "UPDATE saved_searches SET active = ? WHERE id = ?",
        (int(active), search_id),
    )
    conn.commit()


# -- ebay_listings CRUD --

def upsert_listing(
    conn: sqlite3.Connection,
    item_id: str,
    title: str,
    price: float,
    shipping: float = 0,
    condition: str | None = None,
    seller_rating: float | None = None,
    first_seen: int | None = None,
) -> None:
    """INSERT OR REPLACE an eBay listing."""
    if first_seen is None:
        first_seen = int(time.time())
    conn.execute(
        """INSERT OR REPLACE INTO ebay_listings
           (item_id, title, price, shipping, condition, seller_rating, first_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (item_id, title, price, shipping, condition, seller_rating, first_seen),
    )
    conn.commit()


def update_listing_match(
    conn: sqlite3.Connection,
    item_id: str,
    match_release_id: int,
    match_method: str,
    match_score: float,
    deal_score: float,
) -> None:
    """Update match fields on an existing eBay listing."""
    conn.execute(
        """UPDATE ebay_listings
           SET match_release_id = ?, match_method = ?,
               match_score = ?, deal_score = ?
           WHERE item_id = ?""",
        (match_release_id, match_method, match_score, deal_score, item_id),
    )
    conn.commit()


def get_unnotified_deals(
    conn: sqlite3.Connection, min_deal_score: float
) -> list[dict]:
    """Return listings with deal_score >= threshold and not yet notified."""
    rows = conn.execute(
        """SELECT * FROM ebay_listings
           WHERE deal_score >= ? AND notified_at IS NULL""",
        (min_deal_score,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_notified(conn: sqlite3.Connection, item_id: str) -> None:
    """Set notified_at to current timestamp."""
    conn.execute(
        "UPDATE ebay_listings SET notified_at = ? WHERE item_id = ?",
        (int(time.time()), item_id),
    )
    conn.commit()


# -- alert_log CRUD --

def log_alert(
    conn: sqlite3.Connection,
    chat_id: int,
    item_id: str,
    deal_score: float,
) -> None:
    """Insert an alert record."""
    conn.execute(
        """INSERT INTO alert_log (chat_id, item_id, sent_at, deal_score)
           VALUES (?, ?, ?, ?)""",
        (chat_id, item_id, int(time.time()), deal_score),
    )
    conn.commit()


def was_alerted(
    conn: sqlite3.Connection, chat_id: int, item_id: str
) -> bool:
    """Check if an alert was already sent for this chat+item."""
    row = conn.execute(
        "SELECT 1 FROM alert_log WHERE chat_id = ? AND item_id = ?",
        (chat_id, item_id),
    ).fetchone()
    return row is not None
