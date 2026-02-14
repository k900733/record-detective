# Vinyl/CD Detective MVP -- Side Hustle Scope

## Architecture

```
[Discogs API] ──> Price Database (what's a record worth?)
                         |
                         v
[eBay Browse API] ──> Matcher ──> Deal Detector ──> Alerts
                                       |               |
                              "listing < 60% of     Telegram / Email
                               Discogs median"      w/ affiliate link
```

**Key insight:** Discogs is the **pricing oracle**, eBay is the **deal source**. Discogs tells you what things are worth (vinyl, CDs, cassettes -- all formats); eBay is where you find them underpriced.

**Format coverage:** Discogs catalogs all physical music formats (vinyl LPs, 7"/12" singles, CDs, cassettes, box sets). The entire pipeline is format-agnostic -- the same matching and scoring logic applies to a rare CD pressing as to a vinyl first press.

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python | Fast to build, great API libraries |
| Database | SQLite -> PostgreSQL when needed | Zero infra to start |
| Scheduler | APScheduler or cron | No queue infra needed |
| Alerts | Telegram Bot API | Free, instant, mobile push, rich formatting |
| Web UI | FastAPI + HTMX (or skip entirely for V1) | Minimal JS, server-rendered |
| Hosting | $5/mo VPS (Hetzner, DigitalOcean) | Or a Raspberry Pi at home |
| Affiliate | eBay Partner Network | Apply on day 1, ~10 business days approval |

**Monthly cost: $5-10**

---

## Platform API Constraints

| Platform | API Available | Rate Limits | Affiliate Program | Role |
|----------|--------------|-------------|-------------------|------|
| Discogs | Yes | 60 req/min (auth), 25 req/min (unauth) | No | Pricing oracle (all formats: vinyl, CD, cassette) |
| eBay | Yes (Browse API) | ~5,000 calls/day default (increase requestable) | Yes (EPN, 2-4%) | Deal source + revenue |
| Reverb | Yes | TBD | Yes (Awin, 1% physical + $5 new user bonus) | V2 deal source |
| FB Marketplace | No public API | N/A | No | **Avoid -- no legal access** |
| Craigslist | No API | N/A | No | **Avoid -- $60M+ in lawsuits against scrapers** |

**Realistic platform stack: Discogs + eBay (V1), add Reverb (V2).**

---

## Core Components

### 1. Price Database Builder (Discogs API)

- Build a local cache of Discogs median sale prices by release ID
- Seed with genres/labels you care about across all formats (vinyl, CD, cassette)
- Refresh prices weekly (they don't move fast)
- 60 req/min = ~86K lookups/day -- cache aggressively, each release only needs one lookup then periodic refresh

### 2. eBay Deal Scanner (Browse API)

- Poll eBay Browse API with saved search queries every 15-30 min
- Each call returns up to 200 results
- 5,000 calls/day default = up to 1M listings scannable/day
- Extract: title, price, item ID, condition, seller info, images

### 3. Matching Engine

Match eBay listings to Discogs releases for accurate pricing.

**V1 matching strategy (no NLP needed):**

- Catalog number match -- most reliable, ~40% of listings have these
- UPC/barcode match -- when available
- Artist + title + format fuzzy match -- covers another ~30%

**V2 (later):** LLM-powered description parsing for the remaining ~30% with vague titles like "old jazz record lot."

### 4. Deal Scoring

```python
score = (discogs_median - ebay_price) / discogs_median

if score > 0.40:  # 40%+ below median
    alert(priority="high")
elif score > 0.25:  # 25-40% below
    alert(priority="medium")
```

Add modifiers for: seller rating, condition notes, shipping cost, buy-it-now vs auction.

### 5. Alert Delivery

Telegram bot sends formatted deal cards:

- Record title, artist, pressing info
- eBay price vs Discogs median (with % savings)
- Condition
- **Affiliate link** (one tap to buy)

Later: email digest, Discord webhook, web dashboard.

---

## Build Timeline (10-15 hrs/week)

| Week | Deliverable | Hours |
|------|------------|-------|
| 1 | eBay Partner Network application. Discogs API auth + price fetcher. Seed price DB for 2-3 target genres | 12 |
| 2 | eBay Browse API integration. Basic search polling + result parsing | 12 |
| 3 | Matching engine (catalog # + fuzzy). Deal scoring logic | 15 |
| 4 | Telegram bot alerts with affiliate links. End-to-end flow working | 12 |
| 5 | Saved search management (config file or simple DB). Tuning false positives | 10 |
| 6 | Testing with real data. Adjust thresholds. Polish alert formatting | 10 |
| 7-8 | Buffer / refinement / add Reverb API as 3rd source | 10-15 |

**Total: ~6-8 weeks to a working MVP.**

---

## Revenue Math

### eBay Affiliate (from day 1)

| Scenario | Purchases/month | Avg sale | Commission (3%) | Monthly |
|----------|----------------|----------|-----------------|---------|
| Just you | 10 | $35 | $1.05 | $10 |
| 50 users | 200 | $35 | $1.05 | $210 |
| 200 users | 1,000 | $35 | $1.05 | $1,050 |
| 500 users | 3,000 | $35 | $1.05 | $3,150 |

### Optional Pro Tier ($9.99/mo) -- add at month 4-5

- Faster polling (5 min vs 30 min)
- More saved searches (20 vs 5)
- Priority alerts (see deals first)
- 50 subscribers = $500/mo
- 200 subscribers = $2,000/mo

### Realistic 12-Month Target

Affiliate ($500-1,500) + Pro tier ($500-1,000) = **$1,000-2,500/month**

---

## Growth Channels (Free)

1. **Use it yourself** -- post finds on r/vinyl, r/VinylDeals, Discogs forums. Organic credibility.
2. **Telegram group** -- invite collectors, let them see alerts in real-time. Word of mouth.
3. **"Deal of the Day" posts** -- share one great find daily on social media. Builds audience.
4. **Vinyl collector Discord servers** -- many already exist with deal-sharing channels.

---

## What to Skip in V1

| Feature | Why skip | When to add |
|---------|----------|-------------|
| NLP pressing identification | Catalog # matching covers the easy wins first | V2, month 4+ |
| Facebook Marketplace | No API, legal risk | Maybe never |
| Craigslist | $60M in lawsuits against scrapers | Never |
| Mobile app | Telegram bot IS your mobile app | V3 if demand exists |
| Web dashboard | Config file + Telegram is enough to start | V2, month 3-4 |
| User accounts / auth | You're the only user initially | When you open to others |

---

## Key Risks (Side Hustle Context)

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| eBay Partner Network application rejected | Low | Apply with a clean site, clear use case |
| Discogs rate limits too restrictive | Low | Aggressive caching, weekly refresh |
| Matching accuracy too low | Medium | Start with catalog # only, expand gradually |
| Alert fatigue (too many false positives) | Medium | Tune thresholds, add user feedback loop |
| Motivation decay | Medium | Use it yourself -- scratch your own itch |

---

## First Weekend Kickoff Checklist

- [ ] Apply for eBay Partner Network account
- [ ] Register a Discogs API application (get auth token)
- [ ] Set up Python project with `requests`, `sqlite3`, `python-telegram-bot`
- [ ] Write the Discogs price fetcher -- seed 500 releases across vinyl and CD in a genre you know
- [ ] Write the eBay search poller -- get raw results flowing
- [ ] Match one deal by hand end-to-end to validate the concept

If the first weekend feels productive, you have a project. If it feels like a slog, you've spent one weekend instead of six months finding out.

---

## Business Panel Analysis Summary

This scope was informed by a multi-expert panel analysis (Porter, Christensen, Taleb, Kim/Mauborgne, Godin, Meadows). Key strategic findings:

- **The market gap is confirmed** -- no cross-platform deal aggregator exists for vinyl
- **Vinyl market is $1.6-2.4B and growing 6-13% CAGR**, Gen Z driving 27% of purchases
- **20-40% price variance** exists across sellers for the same record (persistent inefficiency)
- **API-only approach is the only legally safe path** -- scraping FB/Craigslist carries multi-million dollar litigation risk
- **Arbitrage value decays over time** -- plan to evolve from "find underpriced records" toward "find records worth owning" (curation) as the market becomes more efficient
- **Comparable platforms** like StockX ($3.8B) and Whatnot ($11.5B) validate the collectibles-tool space, though vinyl TAM is smaller (~$50-100M for tooling)