
import pytest

from app.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    password_hash_needs_update,
    verify_password,
    verify_token,
)


def test_password_hash_uses_argon2id():
    password_hash = hash_password("OpsPilot-Secure-Password-123!")

    assert password_hash.startswith("$argon2id$")
    assert password_hash != "OpsPilot-Secure-Password-123!"


def test_password_hashes_are_salted():
    password = "OpsPilot-Secure-Password-123!"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)


def test_password_verification_accepts_correct_password():
    password = "Correct-Password-123!"
    stored_hash = hash_password(password)

    assert verify_password(password, stored_hash) is True


def test_password_verification_rejects_wrong_password():
    stored_hash = hash_password("Correct-Password-123!")

    assert verify_password("Wrong-Password-123!", stored_hash) is False


def test_password_verification_rejects_invalid_hash():
    assert verify_password("some-password", "not-a-valid-hash") is False


def test_hash_password_rejects_empty_password():
    with pytest.raises(ValueError):
        hash_password("")


def test_password_hash_does_not_need_update():
    stored_hash = hash_password("Correct-Password-123!")

    assert password_hash_needs_update(stored_hash) is False


def test_session_tokens_are_random_and_unique():
    first_token = generate_session_token()
    second_token = generate_session_token()

    assert first_token != second_token
    assert len(first_token) >= 40


def test_csrf_tokens_are_random_and_unique():
    first_token = generate_csrf_token()
    second_token = generate_csrf_token()

    assert first_token != second_token
    assert len(first_token) >= 40


def test_session_and_csrf_tokens_are_independent():
    session_token = generate_session_token()
    csrf_token = generate_csrf_token()

    assert session_token != csrf_token


def test_hash_token_returns_sha256_hex_digest():
    token = generate_session_token()
    token_hash = hash_token(token)

    assert len(token_hash) == 64
    assert all(character in "0123456789abcdef" for character in token_hash)
    assert token_hash != token


def test_same_token_produces_same_hash():
    token = generate_session_token()

    assert hash_token(token) == hash_token(token)


def test_verify_token_accepts_matching_token():
    token = generate_csrf_token()
    stored_hash = hash_token(token)

    assert verify_token(token, stored_hash) is True


def test_verify_token_rejects_different_token():
    original_token = generate_csrf_token()
    different_token = generate_csrf_token()
    stored_hash = hash_token(original_token)

    assert verify_token(different_token, stored_hash) is False


def test_verify_token_rejects_empty_values():
    assert verify_token("", "some-hash") is False
    assert verify_token("some-token", "") is False
