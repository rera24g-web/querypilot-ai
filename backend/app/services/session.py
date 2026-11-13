"""Session management service for authentication."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.orm import Session as DBSession

from app.models.user import User, Session as SessionModel
from app.utils.security import generate_session_token, generate_csrf_token


class SessionService:
    """Service for managing user sessions."""

    # Session duration: 7 days
    SESSION_DURATION = timedelta(days=7)
    # Sliding window: refresh if activity within last 24 hours
    SLIDING_WINDOW = timedelta(hours=24)

    def __init__(self, db: DBSession):
        self.db = db

    def create_session(
        self,
        user: User,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> SessionModel:
        """
        Create a new session for a user.

        Args:
            user: The user to create session for
            user_agent: Optional user agent string
            ip_address: Optional IP address

        Returns:
            Created Session object
        """
        now = datetime.now(timezone.utc)
        session = SessionModel(
            id=generate_session_token(),
            user_id=user.id,
            csrf_token=generate_csrf_token(),
            created_at=now,
            expires_at=now + self.SESSION_DURATION,
            last_activity=now,
            user_agent=user_agent,
            ip_address=ip_address
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: str) -> Optional[SessionModel]:
        """
        Get a session by ID and validate it.

        Args:
            session_id: Session ID to look up

        Returns:
            Session if valid and not expired, None otherwise
        """
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        session = self.db.execute(stmt).scalar_one_or_none()

        if session is None:
            return None

        if session.is_expired():
            self.delete_session(session_id)
            return None

        return session

    def validate_session(self, session_id: str) -> Optional[User]:
        """
        Validate a session and return the associated user.

        Args:
            session_id: Session ID to validate

        Returns:
            User if session is valid, None otherwise
        """
        session = self.get_session(session_id)
        if session is None:
            return None

        # Update last activity (sliding window)
        now = datetime.now(timezone.utc)
        last_activity = session.last_activity
        if last_activity.tzinfo is None:
            # SQLite returns offset-naive, assume UTC
            last_activity = last_activity.replace(tzinfo=timezone.utc)

        if now - last_activity > self.SLIDING_WINDOW:
            session.last_activity = now
            self.db.commit()

        # Return user
        stmt = select(User).where(User.id == session.user_id)
        user = self.db.execute(stmt).scalar_one_or_none()
        return user

    def get_csrf_token(self, session_id: str) -> Optional[str]:
        """
        Get CSRF token for a session.

        Args:
            session_id: Session ID

        Returns:
            CSRF token if session valid, None otherwise
        """
        session = self.get_session(session_id)
        return session.csrf_token if session else None

    def verify_csrf_token(self, session_id: str, csrf_token: str) -> bool:
        """
        Verify a CSRF token against the session.

        Args:
            session_id: Session ID
            csrf_token: CSRF token to verify

        Returns:
            True if valid, False otherwise
        """
        session = self.get_session(session_id)
        if session is None:
            return False
        return session.csrf_token == csrf_token

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session (logout).

        Args:
            session_id: Session ID to delete

        Returns:
            True if session was deleted, False if not found
        """
        stmt = delete(SessionModel).where(SessionModel.id == session_id)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount > 0

    def delete_user_sessions(self, user_id: str) -> int:
        """
        Delete all sessions for a user.

        Args:
            user_id: User ID

        Returns:
            Number of sessions deleted
        """
        stmt = delete(SessionModel).where(SessionModel.user_id == user_id)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.

        Returns:
            Number of sessions deleted
        """
        now = datetime.now(timezone.utc)
        stmt = delete(SessionModel).where(SessionModel.expires_at < now)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def get_user_sessions(self, user_id: str) -> list[SessionModel]:
        """
        Get all active sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of active sessions
        """
        now = datetime.now(timezone.utc)
        stmt = select(SessionModel).where(
            SessionModel.user_id == user_id,
            SessionModel.expires_at > now
        )
        return list(self.db.execute(stmt).scalars().all())