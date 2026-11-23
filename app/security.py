
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)


_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Create an Argon2id password hash."""

    if not isinstance(password, str) or not password:
        raise ValueError("Password must not be empty")

    return _password_hasher.hash(password)


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """Verify a password against its stored Argon2id hash."""

    if not password or not password_hash:
        return False

    try:
        return _password_hasher.verify(password_hash, password)
    except (
        VerifyMismatchError,
        VerificationError,
        InvalidHashError,
        TypeError,
        ValueError,
    ):
        return False


def password_hash_needs_update(password_hash: str) -> bool:
    """Check whether a stored password hash needs rehashing."""

    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, TypeError, ValueError):
        return True


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""

    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a separate cryptographically secure CSRF token."""

    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return a SHA-256 digest of a random token."""

    if not isinstance(token, str) or not token:
        raise ValueError("Token must not be empty")

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(
    supplied_token: str,
    stored_token_hash: str,
) -> bool:
    """Compare a supplied token with its stored SHA-256 digest."""

    if not supplied_token or not stored_token_hash:
        return False

    supplied_hash = hash_token(supplied_token)

    return hmac.compare_digest(
        supplied_hash,
        stored_token_hash,
    )
