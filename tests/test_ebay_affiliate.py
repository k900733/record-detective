"""Tests for EbayClient.make_affiliate_url."""

from urllib.parse import parse_qs, urlparse

from vinyl_detective.ebay import EbayClient
from vinyl_detective.rate_limiter import RateLimiter


def _make_client() -> EbayClient:
    rl = RateLimiter(calls_per_minute=600)
    return EbayClient(app_id="id", cert_id="secret", rate_limiter=rl)


def test_affiliate_url_with_campaign_id():
    client = _make_client()
    url = client.make_affiliate_url("https://www.ebay.com/itm/123", "5338")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["campid"] == ["5338"]
    assert params["mkevt"] == ["1"]
    assert params["mkcid"] == ["1"]
    assert params["mkrid"] == ["711-53200-19255-0"]
    assert params["toolid"] == ["10001"]


def test_affiliate_url_empty_campaign_id():
    client = _make_client()
    original = "https://www.ebay.com/itm/123"
    assert client.make_affiliate_url(original, "") == original


def test_affiliate_url_preserves_existing_params():
    client = _make_client()
    url = client.make_affiliate_url(
        "https://www.ebay.com/itm/123?foo=bar&baz=qux", "5338"
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["foo"] == ["bar"]
    assert params["baz"] == ["qux"]
    assert params["campid"] == ["5338"]
    assert params["mkevt"] == ["1"]
