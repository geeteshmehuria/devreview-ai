"""Tests for JWT and password security utilities."""

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_subject,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_produces_different_output_than_input(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"

    def test_verify_correct_password(self):
        hashed = hash_password("correct-password")
        assert verify_password("correct-password", hashed) is True

    def test_reject_wrong_password(self):
        hashed = hash_password("correct-password")
        assert verify_password("wrong-password", hashed) is False

    def test_hash_is_different_each_time(self):
        """bcrypt uses random salts — same input → different hash."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        # But both should verify
        assert verify_password("same", h1)
        assert verify_password("same", h2)


class TestJWT:
    def test_access_token_contains_correct_subject(self):
        token = create_access_token("user-123")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_refresh_token_type(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_get_token_subject(self):
        token = create_access_token("user-789")
        assert get_token_subject(token) == "user-789"

    def test_tampered_token_raises(self):
        token = create_access_token("user-1")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_token(tampered)

    def test_access_token_extra_claims(self):
        token = create_access_token("user-1", extra={"role": "admin"})
        payload = decode_token(token)
        assert payload.get("role") == "admin"
