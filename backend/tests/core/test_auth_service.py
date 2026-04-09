"""Unit tests for AuthService password safeguards."""

from unittest.mock import Mock

from app.core.auth import AuthService
from app.core.repository import UserRepository


def test_get_password_hash_rejects_password_over_72_utf8_bytes():
    auth_service = AuthService(Mock(spec=UserRepository))

    too_long_password = "A" * 73

    try:
        auth_service.get_password_hash(too_long_password)
        assert False, "Expected ValueError for password above 72-byte bcrypt limit"
    except ValueError as exc:
        assert "72 bytes" in str(exc)


def test_verify_password_returns_false_for_overlong_plain_password():
    auth_service = AuthService(Mock(spec=UserRepository))
    valid_hash = auth_service.get_password_hash("ValidPass123")

    assert auth_service.verify_password("A" * 73, valid_hash) is False
