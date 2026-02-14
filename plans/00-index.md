# Vinyl Detective -- Implementation Plans

## Overview

6 plans, executed in order. Each plan produces independently testable modules. Total: ~40 steps.

## Dependency Graph

```
Plan 1: Foundation ──┬──> Plan 2: Discogs Client ──┐
                     ├──> Plan 3: eBay Client ──────┤
                     │                              v
                     └──> Plan 4: Matching Engine ──┤
                                                    v
                          Plan 5: Scorer + Telegram ─┤
                                                     v
                          Plan 6: Orchestrator + E2E ─┘
```

Plans 2 and 3 can be built in parallel. Plan 4 depends on Plan 1 and uses helpers from Plan 3. Plans 5 and 6 are sequential.

## Plan Summary

| # | Plan | Steps | Key Output |
|---|------|-------|------------|
| 1 | [Project Foundation](01-project-foundation.md) | 9 | Package skeleton, config, DB schema + CRUD, rate limiter |
| 2 | [Discogs Client](02-discogs-client.md) | 7 | Discogs API: release lookup, price stats, search, caching |
| 3 | [eBay Client](03-ebay-client.md) | 6 | eBay API: OAuth2, search, item detail, UPC/catalog extraction |
| 4 | [Matching Engine](04-matching-engine.md) | 6 | 3-tier matcher: catalog no, barcode, fuzzy (rapidfuzz + FTS5) |
| 5 | [Scorer + Telegram](05-deal-scorer-and-telegram.md) | 6 | Deal scoring, message formatting, bot commands, alert sending |
| 6 | [Orchestrator](06-orchestrator-and-integration.md) | 8 | Async loops, pipeline, cleanup, shutdown, E2E test |

## How to Use These Plans

Each step contains:
- **What to build** -- specific module, class, or function
- **Behavior** -- exactly what it should do, inputs/outputs
- **Test** -- a concrete test to validate the step

An AI developer should execute one step at a time, write the code, run the test, then move to the next step. Do not skip ahead.

## Module Map (final state)

```
vinyl_detective/
    __init__.py
    __main__.py          # Entry point, async orchestrator
    config.py            # Env var loading
    db.py                # SQLite schema + CRUD
    rate_limiter.py      # Async rate limiter
    discogs.py           # Discogs API client
    ebay.py              # eBay Browse API client
    matcher.py           # 3-tier matching engine
    scorer.py            # Deal scoring
    telegram_bot.py      # Bot commands + alert formatting
    pipeline.py          # Scan-match-score pipeline + async loops
tests/
    test_config.py
    test_db.py
    test_db_releases.py
    test_db_crud.py
    test_db_fts.py
    test_rate_limiter.py
    test_discogs.py
    test_discogs_release.py
    test_discogs_price.py
    test_discogs_cache.py
    test_discogs_refresh.py
    test_discogs_search.py
    test_ebay_auth.py
    test_ebay_search.py
    test_ebay_affiliate.py
    test_ebay_item.py
    test_ebay_extract.py
    test_matcher.py
    test_matcher_catalog.py
    test_matcher_barcode.py
    test_matcher_fuzzy.py
    test_matcher_unified.py
    test_scorer.py
    test_scorer_filter.py
    test_telegram_format.py
    test_telegram_commands.py
    test_telegram_alerts.py
    test_pipeline.py
    test_poll_loop.py
    test_refresh_loop.py
    test_cleanup.py
    test_main_integration.py
    test_shutdown.py
    test_e2e.py
```
