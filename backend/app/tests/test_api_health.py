"""API health and root endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_root_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "DevReview AI" in data["name"]
    assert "version" in data


@pytest.mark.asyncio
async def test_docs_available_in_debug(client):
    """Swagger docs should be accessible when DEBUG=True."""
    response = await client.get("/api/docs")
    # May redirect or return HTML — just check it doesn't 404
    assert response.status_code in (200, 307)


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client):
    """Reviews endpoint must reject unauthenticated requests."""
    response = await client.get("/api/v1/reviews")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_github_oauth_url_returns_url(client):
    """GitHub OAuth URL endpoint should return a URL even without credentials."""
    response = await client.get("/api/v1/auth/github/url")
    # Without client_id configured, URL will still be structurally valid
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "github.com/login/oauth/authorize" in data["url"]
