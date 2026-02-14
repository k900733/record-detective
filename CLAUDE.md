# CLAUDE.md

# IMPORTANT:
# Always read memory-bank/@architecture.md before writing any code. Include entire database schema.
# Always read memory-bank/@game-design-document.md before writing any code.
# After adding a major feature or completing a milestone, update memory-bank/@architecture.md.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vinyl/CD Detective: a background daemon that finds underpriced physical music listings on eBay by cross-referencing Discogs median sale prices, then sends deal alerts via Telegram with affiliate links. Format-agnostic (vinyl, CD, cassette).

**Architecture:** Discogs (pricing oracle) -> eBay Browse API (deal source) -> Matcher -> Deal Scorer -> Telegram alerts with eBay Partner Network affiliate links.

## Tech Stack

- **Python 3.12+**, minimal dependencies (3 runtime packages)
- **httpx** for async HTTP, **rapidfuzz** for fuzzy matching, **python-telegram-bot v21+** for alerts
- **SQLite** with WAL mode and FTS5 for search — no ORM, raw SQL
- **asyncio** stdlib for scheduling (no APScheduler) — simple task loops with sleep
- **systemd** for process management
- **Dev tools:** pytest, ruff, python-dotenv

## Dev Setup

```bash
python -m venv venv
source venv/bin/activate
pip install httpx rapidfuzz python-telegram-bot
pip install python-dotenv pytest ruff
```

## Architecture Decisions

- Single async Python process, no web server in V1 (Telegram long-polling only)
- No ORM — 4 simple tables, raw SQL is preferred
- No Docker — systemd + venv on a VPS or Raspberry Pi
- SQLite is the cache layer — no Redis or external cache
- FTS5 for full-text search — no Elasticsearch
- Rate limiting implemented in-process (custom `RateLimiter` class, no library)

## Core Pipeline

1. **Price DB Builder** — cache Discogs median prices by release ID, refresh weekly
2. **eBay Deal Scanner** — poll Browse API every 15-30 min via saved search queries
3. **Matching Engine** — 3-tier: catalog number exact match -> barcode/UPC -> fuzzy artist+title (rapidfuzz + FTS5 pre-filter, score cutoff 85)
4. **Deal Scorer** — `(discogs_median - ebay_price) / discogs_median`; high priority at 40%+, medium at 25%+
5. **Telegram Alerts** — formatted deal cards with affiliate links

## Database Schema

4 tables: `discogs_releases`, `ebay_listings`, `saved_searches`, `alert_log`. Plus `releases_fts` (FTS5 virtual table). See `memory-bank/tech-stack.md` for full DDL.

## API Constraints

| API | Rate Limit | Auth |
|-----|-----------|------|
| Discogs | 60 req/min (auth) | Personal access token |
| eBay Browse API | ~5,000 calls/day | OAuth2 client credentials |

## Environment Variables

```
DISCOGS_TOKEN
EBAY_APP_ID
EBAY_CERT_ID
TELEGRAM_TOKEN
```

## Module Entry Point

Run as `python -m vinyl_detective`. Managed by systemd in production.
