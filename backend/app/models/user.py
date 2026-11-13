"""User and Session models for self-hosted authentication."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, ForeignKey, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.sqlite import TEXT as SQLITE_TEXT
from sqlalchemy.orm import relationship
from app.models.base import Base


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    # Use UUID as primary key - compatible with both PostgreSQL and SQLite
    id = Column(
        PG_UUID(as_uuid=True) if False else SQLITE_TEXT,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationship to sessions
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, active={self.is_active})>"


class Session(Base):
    """Session model for server-side session management."""
    __tablename__ = "sessions"

    id = Column(
        PG_UUID(as_uuid=True) if False else SQLITE_TEXT,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(
        PG_UUID(as_uuid=True) if False else SQLITE_TEXT,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    csrf_token = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    last_activity = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length

    # Relationship to user
    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, user_id={self.user_id}, expires={self.expires_at})>"

    def is_expired(self) -> bool:
        """Check if session has expired."""
        # Handle both offset-aware and offset-naive datetimes (SQLite compatibility)
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            # SQLite returns offset-naive, assume UTC
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires

    def is_valid(self) -> bool:
        """Check if session is valid (not expired)."""
        return not self.is_expired()

# Indexes are created in Alembic migration (20241115_selfhosted_auth.py)
# to avoid duplicate index creation during testing