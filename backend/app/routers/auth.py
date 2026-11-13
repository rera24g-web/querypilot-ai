"""Authentication router for registration, login, logout, and user info."""
from datetime import timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from pydantic import EmailStr

from app.schemas.auth import (
    UserCreate,
    UserResponse,
    LoginRequest,
    TokenResponse,
    UserMeResponse,
)
from app.models.user import User
from app.services.session import SessionService
from app.utils.security import hash_password, verify_password
from app.dependencies.auth import get_db, get_current_user, get_optional_user
from app.db import get_engine

router = APIRouter(prefix="/auth", tags=["authentication"])

# Rate limiting configuration (in-memory for simplicity; use Redis in production)
LOGIN_ATTEMPTS = {}  # ip -> [(timestamp, email), ...]
REGISTER_ATTEMPTS = {}  # ip -> [timestamp, ...]
RATE_LIMIT_WINDOW = timedelta(minutes=15)
MAX_LOGIN_ATTEMPTS = 5
MAX_REGISTER_ATTEMPTS = 3


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(attempts_dict: dict, ip: str, max_attempts: int) -> bool:
    """Check if IP has exceeded rate limit. Does NOT record the attempt."""
    from datetime import datetime, timezone as dt_timezone
    now = datetime.now(dt_timezone.utc)

    if ip not in attempts_dict:
        attempts_dict[ip] = []

    # Clean old attempts
    cutoff = now - RATE_LIMIT_WINDOW
    attempts_dict[ip] = [ts for ts in attempts_dict[ip] if ts > cutoff]

    if len(attempts_dict[ip]) >= max_attempts:
        return False

    return True


def record_failed_attempt(attempts_dict: dict, ip: str):
    """Record a failed attempt."""
    from datetime import datetime, timezone as dt_timezone
    now = datetime.now(dt_timezone.utc)
    if ip not in attempts_dict:
        attempts_dict[ip] = []
    attempts_dict[ip].append(now)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    user_data: UserCreate,
    db: DBSession = Depends(get_db)
):
    """
    Register a new user.

    Args:
        request: FastAPI request
        response: FastAPI response (for setting cookies)
        user_data: Registration data (email, password)
        db: Database session

    Returns:
        User info and success message

    Raises:
        HTTPException: 400 if email exists, 429 if rate limited
    """
    client_ip = get_client_ip(request)

    # Rate limiting - record attempt first, then check
    record_failed_attempt(REGISTER_ATTEMPTS, client_ip)
    if not check_rate_limit(REGISTER_ATTEMPTS, client_ip, MAX_REGISTER_ATTEMPTS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later."
        )

    # Check if email already exists
    stmt = select(User).where(User.email == user_data.email)
    existing_user = db.execute(stmt).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash password
    password_hash = hash_password(user_data.password)

    # Create user
    user = User(
        email=user_data.email,
        password_hash=password_hash,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Clear rate limit on successful registration
    if client_ip in REGISTER_ATTEMPTS:
        del REGISTER_ATTEMPTS[client_ip]

    # Create session
    session_service = SessionService(db)
    session = session_service.create_session(
        user,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip
    )

    # Set cookies - secure=False for local testing (use secure=True in production with HTTPS)
    import os
    secure_cookies = os.getenv("SECURE_COOKIES", "false").lower() == "true"

    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        secure=secure_cookies,
        samesite="lax",
        max_age=604800,
        path="/"
    )
    response.set_cookie(
        key="csrf_token",
        value=session.csrf_token,
        httponly=False,
        secure=secure_cookies,
        samesite="lax",
        max_age=604800,
        path="/"
    )

    return TokenResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at
        ),
        message="Registration successful"
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    db: DBSession = Depends(get_db)
):
    """
    Login with email and password.

    Args:
        request: FastAPI request
        response: FastAPI response (for setting cookies)
        credentials: Login credentials (email, password)
        db: Database session

    Returns:
        User info and success message

    Raises:
        HTTPException: 401 if invalid credentials, 429 if rate limited
    """
    client_ip = get_client_ip(request)

    # Rate limiting
    if not check_rate_limit(LOGIN_ATTEMPTS, client_ip, MAX_LOGIN_ATTEMPTS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later."
        )

    # Find user by email
    stmt = select(User).where(User.email == credentials.email)
    user = db.execute(stmt).scalar_one_or_none()

    if not user or not user.is_active:
        record_failed_attempt(LOGIN_ATTEMPTS, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        record_failed_attempt(LOGIN_ATTEMPTS, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Clear failed attempts on successful login
    if client_ip in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[client_ip]

    # Create session
    session_service = SessionService(db)
    session = session_service.create_session(
        user,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip
    )

    # Set cookies - secure=False for local testing (use secure=True in production with HTTPS)
    # We use an environment variable to control this
    import os
    secure_cookies = os.getenv("SECURE_COOKIES", "false").lower() == "true"

    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        secure=secure_cookies,
        samesite="lax",
        max_age=604800,
        path="/"
    )
    response.set_cookie(
        key="csrf_token",
        value=session.csrf_token,
        httponly=False,
        secure=secure_cookies,
        samesite="lax",
        max_age=604800,
        path="/"
    )

    return TokenResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at
        ),
        message="Login successful"
    )


@router.post("/logout", response_model=dict)
async def logout(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db)
):
    """
    Logout current user.

    Args:
        request: FastAPI request
        response: FastAPI response (for clearing cookies)
        db: Database session

    Returns:
        Success message
    """
    session_id = request.cookies.get("session_id")
    if session_id:
        session_service = SessionService(db)
        session_service.delete_session(session_id)

    # Clear cookies
    response.delete_cookie(key="session_id", path="/")
    response.delete_cookie(key="csrf_token", path="/")

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user info.

    Args:
        current_user: Current authenticated user (from dependency)

    Returns:
        User info
    """
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=current_user.created_at
    )


@router.get("/csrf-token", response_model=dict)
async def get_csrf_token(
    request: Request,
    db: DBSession = Depends(get_db)
):
    """
    Get CSRF token for current session (useful for SPA initialization).

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        CSRF token
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    session_service = SessionService(db)
    csrf_token = session_service.get_csrf_token(session_id)

    if not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    return {"csrf_token": csrf_token}