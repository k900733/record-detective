import httpx
import pytest

from vinyl_detective.ebay import EbayAPIError, EbayClient
from vinyl_detective.rate_limiter import RateLimiter

TOKEN_RESPONSE = {"access_token": "test_token", "expires_in": 7200}

SEARCH_RESPONSE = {
    "itemSummaries": [
        {
            "itemId": "v1|111|0",
            "title": "Blue Note BLP-4003 Art Blakey Moanin LP",
            "price": {"value": "29.99", "currency": "USD"},
            "condition": "Used",
            "seller": {"feedbackPercentage": "99.5"},
            "image": {"imageUrl": "https://i.ebayimg.com/images/1.jpg"},
            "itemWebUrl": "https://www.ebay.com/itm/111",
            "shippingOptions": [
                {"shippingCost": {"value": "4.50", "currency": "USD"}}
            ],
        },
        {
            "itemId": "v1|222|0",
            "title": "Miles Davis Kind Of Blue LP",
            "price": {"value": "15.00", "currency": "USD"},
            "condition": "Good",
            "seller": {"feedbackPercentage": "97.0"},
            "image": {"imageUrl": "https://i.ebayimg.com/images/2.jpg"},
            "itemWebUrl": "https://www.ebay.com/itm/222",
        },
    ]
}


def _mock_transport(search_status=200, search_body=None):
    """Mock transport that handles token + search endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/identity/v1/oauth2/token" in url:
            return httpx.Response(200, json=TOKEN_RESPONSE)
        if "/buy/browse/v1/item_summary/search" in url:
            body = search_body if search_body is not None else SEARCH_RESPONSE
            return httpx.Response(search_status, json=body)
        return httpx.Response(404, text="Not mocked")

    return httpx.MockTransport(handler)


def _patched_client(transport: httpx.MockTransport) -> EbayClient:
    client = EbayClient(
        app_id="test_app", cert_id="test_cert", rate_limiter=RateLimiter(600)
    )
    client._client = httpx.AsyncClient(
        transport=transport, base_url="https://api.ebay.com"
    )
    return client


@pytest.mark.asyncio
async def test_search_listings_returns_parsed_items():
    transport = _mock_transport()
    async with _patched_client(transport) as c:
        results = await c.search_listings("blue note vinyl")
    assert len(results) == 2
    first = results[0]
    assert first["item_id"] == "v1|111|0"
    assert first["title"] == "Blue Note BLP-4003 Art Blakey Moanin LP"
    assert first["price"] == 29.99
    assert first["currency"] == "USD"
    assert first["condition"] == "Used"
    assert first["seller_rating"] == "99.5"
    assert first["image_url"] == "https://i.ebayimg.com/images/1.jpg"
    assert first["item_web_url"] == "https://www.ebay.com/itm/111"
    assert first["shipping"] == 4.50
    second = results[1]
    assert second["item_id"] == "v1|222|0"
    assert second["price"] == 15.00
    assert second["shipping"] == 0.0


@pytest.mark.asyncio
async def test_search_listings_empty_results():
    transport = _mock_transport(search_body={"total": 0})
    async with _patched_client(transport) as c:
        results = await c.search_listings("obscure album xyz")
    assert results == []


@pytest.mark.asyncio
async def test_search_listings_error_raises():
    transport = _mock_transport(search_status=401, search_body={})
    async with _patched_client(transport) as c:
        with pytest.raises(EbayAPIError) as exc_info:
            await c.search_listings("blue note")
        assert exc_info.value.status_code == 401
