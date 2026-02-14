import pytest

from vinyl_detective.discogs import DiscogsClient
from vinyl_detective.rate_limiter import RateLimiter


@pytest.fixture
def client():
    return DiscogsClient(token="test_token_123", rate_limiter=RateLimiter(60))


def test_authorization_header(client):
    headers = client._client.headers
    assert headers["authorization"] == "Discogs token=test_token_123"


def test_user_agent_header(client):
    headers = client._client.headers
    assert headers["user-agent"] == "VinylDetective/1.0"


def test_base_url(client):
    assert str(client._client.base_url) == "https://api.discogs.com"


def test_timeout(client):
    assert client._client.timeout.connect == 30.0


@pytest.mark.asyncio
async def test_context_manager():
    async with DiscogsClient("tok", RateLimiter(60)) as c:
        assert c is not None
