"""eBay Browse API client with OAuth2 authentication."""

import time

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
