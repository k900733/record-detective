"""eBay Browse API client with OAuth2 authentication."""

import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from vinyl_detective.rate_limiter import RateLimiter


class EbayAPIError(Exception):
    """Raised on unexpected eBay API responses."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"eBay API {status_code}: {body}")


class EbayClient:
    """Async client for the eBay Browse API."""

    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SCOPE = "https://api.ebay.com/oauth/api_scope"

    def __init__(
        self, app_id: str, cert_id: str, rate_limiter: RateLimiter
    ) -> None:
        self.rate_limiter = rate_limiter
        self._app_id = app_id
        self._cert_id = cert_id
        self._access_token: str | None = None
        self._token_expires: float = 0.0
        self._client = httpx.AsyncClient(
            base_url="https://api.ebay.com",
            headers={"User-Agent": "VinylDetective/1.0"},
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> "EbayClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _ensure_token(self) -> None:
        """Obtain or refresh the OAuth2 client-credentials token."""
        if self._access_token and time.time() < self._token_expires - 60:
            return
        resp = await self._client.post(
            self.TOKEN_URL,
            content="grant_type=client_credentials"
            f"&scope={self.SCOPE}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(self._app_id, self._cert_id),
        )
        if resp.status_code != 200:
            raise EbayAPIError(resp.status_code, resp.text)
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires = time.time() + data["expires_in"]

    async def search_listings(
        self, query: str, limit: int = 200
    ) -> list[dict]:
        """Search eBay Browse API for fixed-price record listings."""
        await self._ensure_token()
        await self.rate_limiter.wait()
        resp = await self._client.get(
            "/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            },
            params={
                "q": query,
                "limit": limit,
                "filter": "buyingOptions:{FIXED_PRICE}",
                "category_ids": "176985",
            },
        )
        if resp.status_code != 200:
            raise EbayAPIError(resp.status_code, resp.text)
        data = resp.json()
        items = data.get("itemSummaries", [])
        results: list[dict] = []
        for item in items:
            shipping = 0.0
            ship_opts = item.get("shippingOptions")
            if ship_opts:
                cost = ship_opts[0].get("shippingCost", {})
                shipping = float(cost.get("value", 0))
            results.append({
                "item_id": item["itemId"],
                "title": item["title"],
                "price": float(item["price"]["value"]),
                "currency": item["price"]["currency"],
                "condition": item.get("condition"),
                "seller_rating": item.get("seller", {}).get(
                    "feedbackPercentage"
                ),
                "image_url": item.get("image", {}).get("imageUrl"),
                "item_web_url": item.get("itemWebUrl"),
                "shipping": shipping,
            })
        return results

    def make_affiliate_url(
        self, item_web_url: str, campaign_id: str = ""
    ) -> str:
        """Append eBay Partner Network tracking params to a listing URL."""
        if not campaign_id:
            return item_web_url
        parsed = urlparse(item_web_url)
        existing = parse_qs(parsed.query, keep_blank_values=True)
        epn_params = {
            "mkevt": "1",
            "mkcid": "1",
            "mkrid": "711-53200-19255-0",
            "campid": campaign_id,
            "toolid": "10001",
        }
        existing.update(epn_params)
        flat = {k: v if isinstance(v, str) else v[0] for k, v in existing.items()}
        new_query = urlencode(flat)
        return urlunparse(parsed._replace(query=new_query))
