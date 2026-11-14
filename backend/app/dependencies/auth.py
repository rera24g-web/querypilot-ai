"""FastAPI authentication dependencies."""
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.db import get_app_engine
from app.services.session import SessionService
from app.models.user import User


# Database dependency
def get_db() -> DBSession:
    """Get database session for auth (writable app database)."""
    engine = get_app_engine()
    db = DBSession(engine)
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    request: Request,
    db: DBSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from session cookie.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        Authenticated User object

    Raises:
        HTTPException: 401 if not authenticated
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_service = SessionService(db)
    user = session_service.validate_session(session_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    request: Request,
    db: DBSession = Depends(get_db)
) -> Optional[User]:
    """
    Get the current user if authenticated, otherwise None.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User if authenticated, None otherwise
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None

    session_service = SessionService(db)
    user = session_service.validate_session(session_id)

    if user is None or not user.is_active:
        return None

    return user


async def get_current_user_id(
    request: Request,
    db: DBSession = Depends(get_db)
) -> str:
    """
    Get the current user's ID (for backward compatibility with store.py).

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User ID string

    Raises:
        HTTPException: 401 if not authenticated
    """
    user = await get_current_user(request, db)
    return user.id