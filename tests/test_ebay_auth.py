import time

import httpx
import pytest

from vinyl_detective.ebay import EbayAPIError, EbayClient
from vinyl_detective.rate_limiter import RateLimiter

TOKEN_RESPONSE = {"access_token": "test_token", "expires_in": 7200}


def _token_transport(status: int = 200, json_body: dict | None = None):
    """Mock transport that handles the OAuth2 token endpoint."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if "/identity/v1/oauth2/token" in str(request.url):
            call_count += 1
            body = json_body if json_body is not None else TOKEN_RESPONSE
            return httpx.Response(status, json=body)
        return httpx.Response(404, text="Not mocked")

    transport = httpx.MockTransport(handler)
    transport.call_count = lambda: call_count  # type: ignore[attr-defined]
    return transport


def _patched_client(transport: httpx.MockTransport) -> EbayClient:
    client = EbayClient(
        app_id="test_app", cert_id="test_cert", rate_limiter=RateLimiter(600)
    )
    client._client = httpx.AsyncClient(
        transport=transport, base_url="https://api.ebay.com"
    )
    return client


@pytest.mark.asyncio
async def test_ensure_token_fetches_on_first_call():
    transport = _token_transport()
    async with _patched_client(transport) as c:
        await c._ensure_token()
        assert c._access_token == "test_token"
        assert transport.call_count() == 1


@pytest.mark.asyncio
async def test_ensure_token_cached_on_second_call():
    transport = _token_transport()
    async with _patched_client(transport) as c:
        await c._ensure_token()
        await c._ensure_token()
        assert transport.call_count() == 1


@pytest.mark.asyncio
async def test_ensure_token_refreshes_when_expired():
    transport = _token_transport()
    async with _patched_client(transport) as c:
        await c._ensure_token()
        assert transport.call_count() == 1
        c._token_expires = time.time() - 1
        await c._ensure_token()
        assert transport.call_count() == 2


@pytest.mark.asyncio
async def test_ensure_token_error_raises():
    transport = _token_transport(status=401)
    async with _patched_client(transport) as c:
        with pytest.raises(EbayAPIError) as exc_info:
            await c._ensure_token()
        assert exc_info.value.status_code == 401
