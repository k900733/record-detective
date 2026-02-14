from __future__ import annotations

import re

import httpx

from vinyl_detective.rate_limiter import RateLimiter

_ARTIST_SUFFIX = re.compile(r"\s*\(\d+\)$")


class DiscogsAPIError(Exception):
    """Raised on unexpected Discogs API responses."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Discogs API {status_code}: {body}")


class DiscogsClient:
    """Async client for the Discogs API."""

    def __init__(self, token: str, rate_limiter: RateLimiter) -> None:
        self.rate_limiter = rate_limiter
        self._client = httpx.AsyncClient(
            base_url="https://api.discogs.com",
            headers={
                "Authorization": f"Discogs token={token}",
                "User-Agent": "VinylDetective/1.0",
            },
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> DiscogsClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def get_release(self, release_id: int) -> dict | None:
        """Fetch a release by ID. Returns parsed dict or None if 404."""
        await self.rate_limiter.wait()
        resp = await self._client.get(f"/releases/{release_id}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise DiscogsAPIError(resp.status_code, resp.text)
        data = resp.json()
        return _parse_release(data)

    async def get_price_stats(self, release_id: int) -> dict | None:
        """Fetch price suggestions for a release. Returns dict or None."""
        await self.rate_limiter.wait()
        resp = await self._client.get(
            f"/marketplace/price_suggestions/{release_id}"
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise DiscogsAPIError(resp.status_code, resp.text)
        data = resp.json()
        vgp = data.get("Very Good Plus (VG+)")
        if vgp is None:
            return None
        good = data.get("Good (G)")
        return {
            "median_price": vgp["value"],
            "low_price": good["value"] if good else None,
        }

    async def search_releases(
        self,
        query: str,
        format_: str | None = None,
        per_page: int = 50,
    ) -> list[dict]:
        """Search Discogs for releases matching a query."""
        await self.rate_limiter.wait()
        params: dict = {"q": query, "type": "release", "per_page": per_page}
        if format_ is not None:
            params["format"] = format_
        resp = await self._client.get("/database/search", params=params)
        if resp.status_code != 200:
            raise DiscogsAPIError(resp.status_code, resp.text)
        results = resp.json().get("results", [])
        return [
            {
                "release_id": r["id"],
                "title": r.get("title", ""),
                "format": r.get("format", []),
                "catalog_no": r.get("catno", ""),
            }
            for r in results
        ]


def _parse_release(data: dict) -> dict:
    """Extract relevant fields from a Discogs release JSON."""
    artist = ""
    if data.get("artists"):
        artist = _ARTIST_SUFFIX.sub("", data["artists"][0].get("name", ""))

    catalog_no = ""
    if data.get("labels"):
        catalog_no = data["labels"][0].get("catno", "")

    barcode = ""
    for ident in data.get("identifiers", []):
        if ident.get("type") == "Barcode" and ident.get("value"):
            barcode = ident["value"]
            break

    fmt = ""
    if data.get("formats"):
        fmt = data["formats"][0].get("name", "")

    return {
        "release_id": data.get("id", 0),
        "artist": artist,
        "title": data.get("title", ""),
        "catalog_no": catalog_no,
        "barcode": barcode,
        "format": fmt,
    }


async def fetch_and_cache_release(
    client: DiscogsClient,
    conn,
    release_id: int,
) -> bool:
    """Fetch release + prices from Discogs and cache in the DB. Returns True on success."""
    from vinyl_detective.db import upsert_release

    release = await client.get_release(release_id)
    if release is None:
        return False

    prices = await client.get_price_stats(release_id)
    median_price = None
    low_price = None
    if prices is not None:
        median_price = prices["median_price"]
        low_price = prices["low_price"]

    upsert_release(
        conn,
        release_id=release["release_id"],
        artist=release["artist"],
        title=release["title"],
        catalog_no=release["catalog_no"],
        barcode=release["barcode"],
        format_=release["format"],
        median_price=median_price,
        low_price=low_price,
    )
    return True

async def refresh_stale_prices(
    client: DiscogsClient,
    conn,
    max_age_days: int = 7,
) -> int:
    """Re-fetch prices for releases whose updated_at is stale. Returns count refreshed."""
    from vinyl_detective.db import get_stale_releases, upsert_release

    stale = get_stale_releases(conn, max_age_days)
    refreshed = 0
    for row in stale:
        rid = row["release_id"]
        try:
            prices = await client.get_price_stats(rid)
            if prices is None:
                continue
            upsert_release(
                conn,
                release_id=rid,
                artist=row["artist"],
                title=row["title"],
                catalog_no=row.get("catalog_no"),
                barcode=row.get("barcode"),
                format_=row.get("format"),
                median_price=prices["median_price"],
                low_price=prices["low_price"],
            )
            refreshed += 1
        except Exception:
            continue
    return refreshed
