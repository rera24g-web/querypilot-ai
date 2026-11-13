"""Supabase Auth integration for QueryPilot AI backend (DEPRECATED).

This module provides JWT token verification for Supabase Auth tokens.
**DEPRECATED**: This is kept for backward compatibility and rollback purposes.
New code should use the self-hosted authentication in:
- app.routers.auth (endpoints)
- app.dependencies.auth (FastAPI dependencies)
- app.services.session (session management)

This module will be removed in a future version after migration is verified.

Requirements:
- Supabase project URL (SUPABASE_URL)
- Supabase JWT secret (SUPABASE_JWT_SECRET) - NOT the service role key
- Expected audience (SUPABASE_AUDIENCE) defaults to 'authenticated'

The module uses 'sub' claim from the token as the user ID.
"""
import os
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# Configuration from environment
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_AUDIENCE = os.getenv("SUPABASE_AUDIENCE", "authenticated")

# OAuth2 scheme for token extraction from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


class AuthError(Exception):
    """Raised when authentication fails."""
    pass


class TokenPayload(BaseModel):
    """Validated JWT payload from Supabase token."""
    sub: str  # User ID (UUID)
    email: Optional[str] = None
    exp: int
    iat: int
    aud: Optional[str] = None
    iss: Optional[str] = None


def _get_config() -> dict:
    """Get authentication configuration, failing if not properly configured."""
    secret = SUPABASE_JWT_SECRET
    url = SUPABASE_URL

    if not secret:
        raise AuthError(
            "SUPABASE_JWT_SECRET is not configured. "
            "Please set this environment variable with your Supabase project's JWT secret. "
            "(NOT the service_role key)"
        )
    if not url:
        raise AuthError(
            "SUPABASE_URL is not configured. "
            "Please set this environment variable to your Supabase project URL."
        )

    return {
        "secret": secret,
        "issuer": f"{url}/",
        "audience": SUPABASE_AUDIENCE,
    }


def verify_token(token: str) -> TokenPayload:
    """
    Verify a Supabase access token and return its payload.

    Args:
        token: JWT access token from Supabase Auth

    Returns:
        TokenPayload with validated claims

    Raises:
        AuthError: If token is invalid, expired, or has wrong claims
    """
    config = _get_config()

    # Determine allowed algorithms based on secret type
    # HS256 requires the JWT secret to be a string
    # RS256 requires the JWT secret to be an RSA public key
    # Supabase provides both options - default to RS256 for production
    allowed_algorithms = ["RS256", "HS256"]

    try:
        # Decode and verify the token
        payload = jwt.decode(
            token,
            config["secret"],
            algorithms=allowed_algorithms,
            audience=config["audience"],
            issuer=config["issuer"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["exp", "iat", "sub"],
            }
        )

        return TokenPayload(**payload)

    except JWTError as e:
        raise AuthError(f"Token verification failed: {e}")


def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """
    FastAPI dependency that extracts and validates the user from the Authorization header.

    Uses Bearer token authentication. Returns the user ID (sub claim).

    Args:
        token: Access token from Authorization header (extracted by OAuth2PasswordBearer)

    Returns:
        User ID string from the verified token

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload.sub


def get_current_user_or_none(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """
    Variant that returns None instead of raising for invalid tokens.
    Useful for endpoints that may have different auth requirements.

    Returns:
        User ID if authenticated, None otherwise
    """
    if not token:
        return None

    try:
        payload = verify_token(token)
        return payload.sub
    except AuthError:
        return None