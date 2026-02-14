# Vinyl/CD Detective -- Tech Stack

## Core Principle

Start with the fewest dependencies possible. Every library you don't add is one that can't break. This app is a **background daemon that polls APIs and sends Telegram messages** -- not a web app.

---

## The Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Language | **Python 3.12+** | stdlib gives you sqlite3, asyncio, logging, json, re |
| HTTP Client | **httpx** | Async, connection pooling, retries, timeouts |
| Fuzzy Matching | **rapidfuzz** | 10-50x faster than thefuzz, C++ backend, MIT license |
| Alerts & Commands | **python-telegram-bot v21+** | Async, long-polling mode (no web server needed) |
| Database | **SQLite** (stdlib) | WAL mode, FTS5 for search. Most tested software on earth. |
| Scheduling | **asyncio** (stdlib) | Simple task loops with sleep. No scheduler library needed. |
| Logging | **logging** (stdlib) | Built-in. Works fine. |
| Process Manager | **systemd** | Auto-restart on crash, log management, boot startup |
| Hosting | **Hetzner CPX11** or **Raspberry Pi 4** | VPS: $4.51/mo. Pi: $0/mo after hardware (USB SSD recommended for DB). |

**Total third-party dependencies: 3 packages.**

```txt
httpx>=0.27
rapidfuzz>=3.10
python-telegram-bot>=21.0
```

**Monthly cost: $0-5** (Pi = $0, VPS = ~$5)

---

## Why Not...

| Temptation | Why Skip |
|------------|----------|
| **FastAPI / any web framework** | No web UI in V1. Telegram bot uses long-polling (no server needed). Add FastAPI when you build a dashboard. |
| **SQLAlchemy / any ORM** | 4 simple tables. Raw SQL is clearer and has zero abstraction leaks. |
| **aiosqlite** | SQLite on local NVMe is sub-millisecond. Async wrapper adds complexity for no real gain. Run queries in `asyncio.to_thread()` if needed. |
| **APScheduler** | `asyncio.create_task()` + `asyncio.sleep()` handles periodic polling. No library needed for "run this every 30 minutes." |
| **Docker** | One Python process on one VPS. A systemd unit file + venv is simpler, faster, and has fewer failure modes. |
| **Redis / cachetools** | SQLite IS your cache. Discogs prices live in the DB. No second caching layer needed. |
| **Elasticsearch / Meilisearch** | SQLite FTS5 handles full-text search at this scale. |
| **Celery / message queue** | Single process. No distributed workers. No queue needed. |
| **React / Vue** | Telegram is your V1 frontend. When you need web UI, use FastAPI + HTMX (server-rendered, minimal JS). |
| **AWS / GCP / Azure** | Cost blowout risk. A $5 VPS runs this workload with 99%+ uptime. |

---

## Architecture

```
                    Single Python Process (systemd managed)
                    ========================================

   Telegram Bot (long-polling)          asyncio Task Loops
   +--------------------------+         +---------------------------+
   | /add_search "blue note"  |         | poll_ebay()    every 30m  |
   | /set_threshold 0.30      |         | refresh_discogs()  weekly |
   | /my_searches             |         | cleanup_stale()    daily  |
   | /pause / /resume         |         +---------------------------+
   +--------------------------+                    |
              |                                    |
              v                                    v
         +---------+     +----------+     +--------------+
         | SQLite  |<--->| Matcher  |<--->| Deal Scorer  |
         | (WAL)   |     | rapidfuzz|     | price delta  |
         +---------+     +----------+     +--------------+
                                                 |
                                                 v
                                          Telegram Alert
                                          + affiliate link
```

No web server. No message queue. No external cache. One process, one database file, one config.

---

## Database

SQLite with WAL mode. All persistence in one file.

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000;  -- 64MB (reduce to -16000 on 1GB Raspberry Pi)

CREATE TABLE discogs_releases (
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

CREATE TABLE ebay_listings (
    item_id          TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    price            REAL NOT NULL,
    shipping         REAL DEFAULT 0,
    condition        TEXT,
    seller_rating    REAL,
    match_release_id INTEGER REFERENCES discogs_releases(release_id),
    match_method     TEXT,    -- catalog_no | barcode | fuzzy
    match_score      REAL,
    deal_score       REAL,
    notified_at      INTEGER,
    first_seen       INTEGER
);

CREATE TABLE saved_searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    query           TEXT NOT NULL,
    min_deal_score  REAL DEFAULT 0.25,
    poll_minutes    INTEGER DEFAULT 30,
    active          INTEGER DEFAULT 1
);

CREATE TABLE alert_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    item_id    TEXT NOT NULL,
    sent_at    INTEGER NOT NULL,
    deal_score REAL
);

-- FTS5 for fast artist+title matching
CREATE VIRTUAL TABLE releases_fts USING fts5(
    artist, title, catalog_no,
    content = discogs_releases,
    content_rowid = release_id
);

CREATE INDEX idx_releases_catalog ON discogs_releases(catalog_no);
CREATE INDEX idx_releases_barcode ON discogs_releases(barcode);
CREATE INDEX idx_listings_match   ON ebay_listings(match_release_id);
CREATE INDEX idx_searches_chat    ON saved_searches(chat_id);
```

---

## Scheduling (stdlib asyncio)

No library needed. Simple loops:

```python
async def poll_ebay_loop(db, bot):
    while True:
        searches = get_active_searches(db)
        for search in searches:
            listings = await fetch_ebay_listings(search.query)
            deals = match_and_score(db, listings)
            for deal in deals:
                await send_alert(bot, search.chat_id, deal)
        await asyncio.sleep(30 * 60)  # 30 min

async def refresh_discogs_loop(db):
    while True:
        stale = get_stale_releases(db, max_age_days=7)
        for release in stale:
            price = await fetch_discogs_price(release.release_id)
            update_price(db, release.release_id, price)
        await asyncio.sleep(24 * 60 * 60)  # daily check

async def main():
    db = init_db("vinyl_detective.db")
    bot = TelegramBot(token=TELEGRAM_TOKEN)
    await asyncio.gather(
        bot.run_polling(),
        poll_ebay_loop(db, bot),
        refresh_discogs_loop(db),
    )
```

---

## API Integration

### Discogs (pricing oracle)

- Auth: personal access token (free, 60 req/min)
- Use `httpx.AsyncClient` with rate limiting
- Cache prices in SQLite, refresh weekly
- 60 req/min = ~86K lookups/day (more than enough with caching)

### eBay Browse API (deal source)

- Auth: OAuth2 client credentials
- No official Python SDK for RESTful Browse API (`ebaysdk-python` is for legacy APIs only)
- Use `httpx.AsyncClient` directly
- 5,000 calls/day default, each returns up to 200 results

### Rate Limiting (no library needed)

```python
class RateLimiter:
    def __init__(self, calls_per_minute: int):
        self.interval = 60.0 / calls_per_minute
        self.lock = asyncio.Lock()
        self.last_call = 0.0

    async def wait(self):
        async with self.lock:
            now = asyncio.get_event_loop().time()
            wait_time = self.interval - (now - self.last_call)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_call = asyncio.get_event_loop().time()

discogs_limiter = RateLimiter(calls_per_minute=55)  # margin under 60
```

---

## Matching Pipeline

Three tiers, ordered by confidence:

1. **Catalog number** (~40% of listings) -- normalize and exact-match
2. **Barcode/UPC** (when available) -- direct lookup
3. **Fuzzy artist+title** (~30%) -- rapidfuzz with FTS5 pre-filtering

```python
import re
from rapidfuzz import process, fuzz

def normalize_catalog(cat_no: str) -> str:
    return re.sub(r'[\s\-_.]', '', cat_no.upper())

def match_listing(db, ebay_title: str, ebay_details: dict) -> tuple | None:
    # Tier 1: catalog number
    cat_no = extract_catalog_no(ebay_title)
    if cat_no:
        match = lookup_by_catalog(db, normalize_catalog(cat_no))
        if match:
            return match, 'catalog_no', 1.0

    # Tier 2: barcode
    upc = ebay_details.get('upc')
    if upc:
        match = lookup_by_barcode(db, upc)
        if match:
            return match, 'barcode', 1.0

    # Tier 3: fuzzy match (pre-filter via FTS5, then rank with rapidfuzz)
    candidates = fts5_search(db, ebay_title, limit=50)
    if candidates:
        names = [f"{c['artist']} {c['title']}" for c in candidates]
        result = process.extractOne(
            ebay_title, names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=85
        )
        if result:
            return candidates[result[2]], 'fuzzy', result[1] / 100.0

    return None
```

---

## Deployment

### systemd unit file

```ini
# /etc/systemd/system/vinyl-detective.service
[Unit]
Description=Vinyl Detective Deal Finder
After=network.target

[Service]
Type=simple
User=vinyl
WorkingDirectory=/opt/vinyl-detective
ExecStart=/opt/vinyl-detective/venv/bin/python -m vinyl_detective
Restart=always
RestartSec=10
EnvironmentFile=/opt/vinyl-detective/.env

[Install]
WantedBy=multi-user.target
```

```bash
# Deploy (VPS)
ssh vps 'cd /opt/vinyl-detective && git pull && systemctl restart vinyl-detective'

# Deploy (Raspberry Pi -- local)
cd /opt/vinyl-detective && git pull && sudo systemctl restart vinyl-detective
```

### .env

```
DISCOGS_TOKEN=your_token
EBAY_APP_ID=your_app_id
EBAY_CERT_ID=your_cert_id
TELEGRAM_TOKEN=your_bot_token
```

### Raspberry Pi Notes

- **Recommended model:** Pi 4 (2GB+). Pi 3 works but tighter on RAM.
- **Storage:** Use a USB SSD for the SQLite DB file. SD cards degrade under sustained writes; WAL mode helps but doesn't eliminate the risk.
- **Power:** Use a quality PSU (3A+ for Pi 4). Sudden power loss can corrupt SQLite. A UPS HAT ($15-25) eliminates this risk.
- **Network:** Ethernet preferred over WiFi for reliable API polling.
- **OS:** Use 64-bit Raspberry Pi OS. `rapidfuzz` publishes `aarch64` wheels on PyPI. On 32-bit `armv7l`, you may need to compile from source.
- **Memory:** Reduce `PRAGMA cache_size` to `-16000` (16MB) on 1GB Pi models.

---

## When to Add Complexity

Add each only when you feel the pain, not before:

| Pain Point | Solution | Trigger |
|-----------|----------|---------|
| Need crash tracking across users | Add **sentry-sdk** | Multiple users, can't rely on checking logs manually |
| Need a web dashboard | Add FastAPI + HTMX | Users ask for it, or Telegram bot commands get unwieldy |
| SQLite write contention | Migrate to PostgreSQL | >100 concurrent writers |
| Need reproducible deploys | Add Docker | Handing project to someone else, or multi-service setup |
| Dynamic per-user schedules at scale | Add APScheduler | Managing 500+ users with different polling intervals |
| Need shared state across processes | Add Redis | Running multiple worker processes |
| CPU-bound matching bottleneck | Add Celery + workers | Matching can't keep up in single process |
| Need search beyond FTS5 | Add PostgreSQL pg_trgm | Need trigram similarity or multilingual ranking |

---

## Dev Setup

```bash
python -m venv venv
source venv/bin/activate
pip install httpx rapidfuzz python-telegram-bot
pip install python-dotenv pytest ruff  # dev tools
```

3 runtime dependencies. That's the whole stack.
