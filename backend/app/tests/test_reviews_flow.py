"""End-to-end review flow with the AI provider and Redis mocked out."""

import os
import uuid

import pytest

from app.ai.response_formatter import build_response
from app.core.exceptions import AIProviderError
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import repository_service, review_service

AI_DATA = {
    "overall_score": 72,
    "risk_score": 30,
    "language": "python",
    "ai_summary": "Looks fine.",
    "category_scores": [{"category": "security", "score": 80, "summary": "ok", "suggestions": []}],
    "security_findings": [{"severity": "high", "title": "SQLi", "description": "d", "extra": {"cwe_id": "CWE-89"}}],
    "performance_findings": [
        {"severity": "medium", "title": "N+1", "description": "d", "code_snippet": "for x in y", "extra": {"impact": "slow"}}
    ],
    "code_smells": [{"severity": "low", "title": "Long Method", "description": "d"}],
    "technical_debt": [
        {"severity": "high", "title": "No tests", "description": "d", "extra": {"estimated_hours": 4, "category": "testing"}}
    ],
}


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value


@pytest.fixture
async def auth_client(client, db_session):
    user = User(github_id=uuid.uuid4().int % 10**9, github_login=f"user-{uuid.uuid4().hex[:6]}")
    db_session.add(user)
    await db_session.flush()

    fake_redis = FakeRedis()

    async def override_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = override_redis
    client.headers["Authorization"] = f"Bearer {create_access_token(str(user.id))}"
    yield client


@pytest.mark.asyncio
async def test_code_review_persists_all_findings(auth_client, monkeypatch):
    calls = []

    async def fake_run_review(request, preferred=None):
        calls.append(request)
        return build_response(AI_DATA, "gemini", "test-model")

    monkeypatch.setattr(review_service, "run_review", fake_run_review)
    body = {"content": "def f(x):\n    return x * 2\n", "language": "python"}

    response = await auth_client.post("/api/v1/reviews/code", json=body)
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["status"] == "completed"
    assert len(review["performance_findings"]) == 1          # regression: C3 (code_snippet kwarg)
    assert review["security_findings"][0]["extra"]["cwe_id"] == "CWE-89"
    assert review["code_smells"][0]["title"] == "Long Method"

    # Identical request hits the cache, but still stores the full findings (M7)
    cached = (await auth_client.post("/api/v1/reviews/code", json=body)).json()
    assert len(calls) == 1
    assert len(cached["technical_debt"]) == 1

    detail = await auth_client.get(f"/api/v1/reviews/{review['id']}")
    assert detail.status_code == 200 and len(detail.json()["category_scores"]) == 1

    debt = (await auth_client.get("/api/v1/reviews/debt")).json()
    assert len(debt) == 2 and debt[0]["estimated_hours"] == 4


@pytest.mark.asyncio
async def test_failed_review_is_saved_as_failed(auth_client, monkeypatch):
    async def failing_run_review(request, preferred=None):
        raise AIProviderError("All AI providers failed")

    monkeypatch.setattr(review_service, "run_review", failing_run_review)
    response = await auth_client.post("/api/v1/reviews/code", json={"content": "print('hello world')"})
    assert response.status_code == 503

    history = (await auth_client.get("/api/v1/reviews")).json()
    assert history["items"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_review_works_when_redis_is_down(auth_client, monkeypatch):
    """The cache is optional: a Redis outage must not break reviews."""
    import redis.asyncio as aioredis

    class DownRedis:
        async def get(self, key):
            raise aioredis.ConnectionError("redis unavailable")

        async def setex(self, key, ttl, value):
            raise aioredis.ConnectionError("redis unavailable")

    async def override_redis():
        yield DownRedis()

    async def fake_run_review(request, preferred=None):
        return build_response(AI_DATA, "gemini", "test-model")

    app.dependency_overrides[get_redis] = override_redis
    monkeypatch.setattr(review_service, "run_review", fake_run_review)
    response = await auth_client.post("/api/v1/reviews/code", json={"content": "x = compute(1, 2)"})
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_invalid_uuid_returns_422(auth_client):
    assert (await auth_client.get("/api/v1/reviews/not-a-uuid")).status_code == 422
    assert (await auth_client.delete("/api/v1/repositories/not-a-uuid")).status_code == 422


@pytest.mark.asyncio
async def test_list_github_repos(auth_client, monkeypatch):
    repo = {
        "full_name": "octo/hello", "name": "hello", "description": None,
        "url": "https://github.com/octo/hello", "language": "Python", "stars": 3,
        "is_private": True, "updated_at": "2026-11-01T00:00:00+00:00",
    }
    tokens = []
    monkeypatch.setattr(repository_service, "get_github_token", lambda user: "gh-token")
    monkeypatch.setattr(repository_service, "_fetch_user_repos", lambda token: tokens.append(token) or [repo])

    response = await auth_client.get("/api/v1/repositories/github")
    assert response.status_code == 200, response.text
    assert response.json() == [repo]
    assert tokens == ["gh-token"]


@pytest.mark.asyncio
async def test_list_github_repos_without_stored_token_asks_to_sign_in(auth_client):
    response = await auth_client.get("/api/v1/repositories/github")
    assert response.status_code == 401
    assert "sign in again" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_github_repos_requires_auth(client):
    assert (await client.get("/api/v1/repositories/github")).status_code == 401


def test_repo_sampling_skips_symlinks(tmp_path):
    """C1: a symlink in a cloned repo must never be read (it could point at server secrets)."""
    secret = tmp_path / "secret.env"
    secret.write_text("JWT_SECRET_KEY=top-secret")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')")
    try:
        os.symlink(secret, repo / "README.md")
        os.symlink(secret, repo / "leak.py")
    except OSError:
        pytest.skip("symlinks not permitted on this platform")

    content = repository_service._extract_repo_content(str(repo))
    assert "top-secret" not in content
    assert "print('hi')" in content


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/octo/hello", ("octo", "hello")),
        ("https://github.com/octo/hello.git", ("octo", "hello")),
        ("https://github.com/octo/hello/tree/main/src", ("octo", "hello")),
    ],
)
def test_parse_repo_url(url, expected):
    assert repository_service.parse_repo_url(url) == expected
