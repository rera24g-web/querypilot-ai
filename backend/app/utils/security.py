"""Security utilities for password hashing and token generation."""
import os
import secrets
from passlib.context import CryptContext
from typing import Optional

# Argon2id configuration for password hashing
pwd_context = CryptContext(
    schemes=["argon2"],
    default="argon2",
    argon2__time_cost=3,
    argon2__memory_cost=65536,
    argon2__parallelism=4,
    argon2__hash_len=32,
    argon2__salt_size=16,
)

# Session token length (32 bytes = 256 bits)
SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.

    Args:
        password: Plain text password

    Returns:
        Argon2id hash string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored Argon2id hash

    Returns:
        True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def generate_session_token() -> str:
    """
    Generate a cryptographically secure session token.

    Returns:
        URL-safe base64 encoded token
    """
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def generate_csrf_token() -> str:
    """
    Generate a cryptographically secure CSRF token.

    Returns:
        URL-safe base64 encoded token
    """
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def constant_time_compare(val1: str, val2: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks.

    Args:
        val1: First string
        val2: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    return secrets.compare_digest(val1, val2)


def get_password_hash_info(hashed_password: str) -> Optional[dict]:
    """
    Extract hash algorithm info for potential future upgrades.

    Args:
        hashed_password: The stored hash

    Returns:
        Dictionary with hash info or None if invalid
    """
    try:
        # Check if it's an Argon2 hash
        if hashed_password.startswith("$argon2"):
            return {"algorithm": "argon2", "needs_rehash": False}
        return {"algorithm": "unknown", "needs_rehash": True}
    except Exception:
        return None