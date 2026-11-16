"""Tests for JWT, OAuth state and secret-encryption utilities."""

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_state_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    get_token_subject,
)


class TestJWT:
    def test_access_token_contains_correct_subject(self):
        payload = decode_token(create_access_token("user-123"))
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_refresh_token_type(self):
        assert decode_token(create_refresh_token("user-456", "sid"))["type"] == "refresh"

    def test_state_token_type(self):
        assert decode_token(create_state_token())["type"] == "oauth_state"

    def test_get_token_subject(self):
        assert get_token_subject(create_access_token("user-789")) == "user-789"

    def test_tampered_token_raises(self):
        token = create_access_token("user-1")
        with pytest.raises(jwt.PyJWTError):
            decode_token(token[:-5] + "XXXXX")

    def test_access_token_extra_claims(self):
        assert decode_token(create_access_token("user-1", extra={"role": "admin"})).get("role") == "admin"


class TestSecretEncryption:
    def test_round_trip_and_not_plaintext(self):
        encrypted = encrypt_secret("gho_secret")
        assert "gho_secret" not in encrypted
        assert decrypt_secret(encrypted) == "gho_secret"

    def test_undecryptable_values_return_none(self):
        assert decrypt_secret("legacy-plaintext-token") is None
        assert decrypt_secret(None) is None
