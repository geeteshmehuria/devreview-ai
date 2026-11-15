"""File filters and secret redaction for RAG indexing."""

import pytest

from app.rag.sanitize import REDACTED, redact_secrets, should_index_content, should_index_path


@pytest.mark.parametrize("path", [
    "app/main.py", "frontend/lib/api/client.ts", "README.md", "docker-compose.yml",
    "backend/Dockerfile", "Makefile", "pyproject.toml", "frontend/package.json",
])
def test_useful_files_are_indexed(path):
    assert should_index_path(path)


@pytest.mark.parametrize("path", [
    ".env", ".env.local", "backend/.env.example", "certs/server.pem", "keys/private.key", "id_rsa",
    "package-lock.json", "yarn.lock", "poetry.lock", "go.sum", "static/app.min.js", "dist/app.js.map",
    "image.png", "archive.zip",
])
def test_secret_lock_minified_and_binary_files_are_skipped(path):
    assert not should_index_path(path)


def test_content_filter():
    assert should_index_content("print('hi')\n", max_chars=100)
    assert not should_index_content("x" * 101, max_chars=100)                 # too big
    assert not should_index_content("abc\x00def", max_chars=100)              # binary
    assert not should_index_content("var a=1;" * 200, max_chars=10_000)       # minified (one huge line)
    assert not should_index_content("   \n", max_chars=100)                   # empty


@pytest.mark.parametrize("secret", [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_" + "a" * 36,
    "github_pat_" + "B" * 30,
    "AIza" + "c" * 35,
    "sk-proj-" + "d" * 30,
    "sk-ant-" + "e" * 30,
    "sk_live_" + "f" * 24,
    "xoxb-123456789012-abcdef",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
])
def test_known_token_formats_are_redacted(secret):
    out = redact_secrets(f'client = Client(key="{secret}")')
    assert secret not in out and REDACTED in out


def test_assignments_redact_the_value_but_keep_the_name():
    out = redact_secrets('DB_PASSWORD = "hunter2-very-secret"\napi_key: \'abcdefgh12345\'')
    assert "hunter2" not in out and "abcdefgh12345" not in out
    assert "DB_PASSWORD" in out and "api_key" in out


def test_normal_code_is_untouched():
    code = (
        'password = get_password()\ntoken = request.headers["Authorization"]\nTOKEN_TTL = 900\n'
        'GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"\n'
    )
    assert redact_secrets(code) == code


def test_url_credentials_are_redacted():
    out = redact_secrets("DATABASE_URL=postgresql://admin:s3cretpw@db.example.com:5432/app")
    assert "s3cretpw" not in out and "db.example.com" in out


def test_private_key_block_redaction_keeps_line_numbers():
    text = "a = 1\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----\nb = 2\n"
    out = redact_secrets(text)
    assert "MIIEow" not in out
    assert out.count("\n") == text.count("\n")
    assert out.splitlines()[5] == "b = 2"
