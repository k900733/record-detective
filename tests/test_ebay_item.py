"""Tests for EbayClient.get_item detail fetch."""

import httpx
import pytest

from vinyl_detective.ebay import EbayClient, EbayAPIError
from vinyl_detective.rate_limiter import RateLimiter

TOKEN_RESPONSE = {"access_token": "tok", "expires_in": 7200}

ITEM_RESPONSE = {
    "itemId": "v1|123|0",
    "title": "Blue Note BLP-4003 Art Blakey Moanin LP",
    "description": "<p>Original pressing, VG+ condition.</p>",
    "localizedAspects": [
        {"type": "STRING", "name": "Format", "value": "Vinyl"},
        {"type": "STRING", "name": "UPC", "value": "602547000000"},
        {"type": "STRING", "name": "Record Label", "value": "Blue Note"},
    ],
    "itemLocation": {"city": "Portland", "stateOrProvince": "OR", "country": "US"},
    "price": {"value": "49.99", "currency": "USD"},
    "condition": "Used",
    "itemWebUrl": "https://www.ebay.com/itm/123",
}


@pytest.mark.asyncio
async def test_get_item_returns_parsed_details():
    transport = httpx.MockTransport(
        lambda req: (
            httpx.Response(200, json=TOKEN_RESPONSE)
            if "oauth2/token" in str(req.url)
            else httpx.Response(200, json=ITEM_RESPONSE)
        )
    )
    rl = RateLimiter(calls_per_minute=600)
    client = EbayClient(app_id="id", cert_id="secret", rate_limiter=rl)
    client._client = httpx.AsyncClient(transport=transport, base_url="https://api.ebay.com")
    async with client:
        result = await client.get_item("v1|123|0")

    assert result is not None
    assert result["item_id"] == "v1|123|0"
    assert result["title"] == "Blue Note BLP-4003 Art Blakey Moanin LP"
    assert result["description"] == "<p>Original pressing, VG+ condition.</p>"
    assert result["price"] == 49.99
    assert result["currency"] == "USD"
    assert result["condition"] == "Used"
    assert result["item_location"]["city"] == "Portland"
    # UPC extractable from localized_aspects
    upcs = [a for a in result["localized_aspects"] if a["name"] == "UPC"]
    assert len(upcs) == 1
    assert upcs[0]["value"] == "602547000000"


@pytest.mark.asyncio
async def test_get_item_returns_none_on_404():
    transport = httpx.MockTransport(
        lambda req: (
            httpx.Response(200, json=TOKEN_RESPONSE)
            if "oauth2/token" in str(req.url)
            else httpx.Response(404, text="Not Found")
        )
    )
    rl = RateLimiter(calls_per_minute=600)
    client = EbayClient(app_id="id", cert_id="secret", rate_limiter=rl)
    client._client = httpx.AsyncClient(transport=transport, base_url="https://api.ebay.com")
    async with client:
        result = await client.get_item("v1|999|0")

    assert result is None


@pytest.mark.asyncio
async def test_get_item_raises_on_server_error():
    transport = httpx.MockTransport(
        lambda req: (
            httpx.Response(200, json=TOKEN_RESPONSE)
            if "oauth2/token" in str(req.url)
            else httpx.Response(500, text="Internal Server Error")
        )
    )
    rl = RateLimiter(calls_per_minute=600)
    client = EbayClient(app_id="id", cert_id="secret", rate_limiter=rl)
    client._client = httpx.AsyncClient(transport=transport, base_url="https://api.ebay.com")
    async with client:
        with pytest.raises(EbayAPIError) as exc_info:
            await client.get_item("v1|123|0")
    assert exc_info.value.status_code == 500
