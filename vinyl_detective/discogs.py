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
