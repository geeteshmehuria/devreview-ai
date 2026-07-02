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
async def test_github_oauth_url_returns_url(client, monkeypatch):
    """GitHub OAuth URL endpoint returns an encoded authorize URL + CSRF state."""
    from urllib.parse import parse_qs, urlparse

    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GITHUB_CALLBACK_URL", "https://example.com/callback")

    response = await client.get("/api/v1/auth/github/url")
    assert response.status_code == 200
    data = response.json()
    assert "github.com/login/oauth/authorize" in data["url"]

    query = parse_qs(urlparse(data["url"]).query)
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["https://example.com/callback"]
    # State must be present in both the URL and the response body, and match
    assert data["state"] == query["state"][0]
    assert len(data["state"]) >= 32


@pytest.mark.asyncio
async def test_github_oauth_url_unconfigured_returns_500(client, monkeypatch):
    """Without a client id, the endpoint must fail loudly — not emit a broken URL."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "")

    response = await client.get("/api/v1/auth/github/url")
    assert response.status_code == 500


def test_user_public_accepts_uuid_id():
    """Regression: ORM returns UUID PKs; UserPublic must coerce them to str."""
    from uuid import uuid4

    from app.schemas.auth import UserPublic

    uid = uuid4()
    user = UserPublic(
        id=uid,
        github_login="octocat",
        github_name=None,
        github_avatar_url=None,
        github_email=None,
        role="user",
    )
    assert user.id == str(uid)
