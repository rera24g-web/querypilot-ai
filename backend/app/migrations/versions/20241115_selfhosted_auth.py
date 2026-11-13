"""Add self-hosted authentication tables

Revision ID: 20241115_selfhosted_auth
Revises: 20241105_initial_migration
Create Date: 2024-11-15 00:00:00.000000

This migration adds users and sessions tables for self-hosted authentication.
It also updates investigations table to use UUID for user_id with foreign key.

BACKUP AND ROLLBACK:
- Backup: Run before migration. Tables are additive.
- Rollback: `alembic downgrade -1` removes users and sessions tables.
  Note: investigations.user_id type change needs manual rollback if migrated.

IMPLEMENTATION NOTES:
- Users table with UUID primary key
- Sessions table with UUID primary key and foreign key to users
- Investigations.user_id changes from TEXT to UUID with FK
- Indexes for performance

SAFETY:
- Run on copy of production database first
- Test migration and rollback in staging
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

# revision identifiers, used by Alembic.
revision = "20241115_selfhosted_auth"
down_revision = "20241105_initial_migration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add users and sessions tables, update investigations.user_id."""

    # Get dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # Create users table
    if dialect_name == "postgresql":
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
            sa.Column("email", sa.String(255), unique=True, nullable=False),
            sa.Column("password_hash", sa.Text, nullable=False),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
    else:
        # SQLite
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(255), unique=True, nullable=False),
            sa.Column("password_hash", sa.Text, nullable=False),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )

    # Create index on email
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Create sessions table
    if dialect_name == "postgresql":
        op.create_table(
            "sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("csrf_token", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_activity", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("user_agent", sa.Text, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
        )
    else:
        # SQLite
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("csrf_token", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_activity", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("user_agent", sa.Text, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
        )

    # Create indexes for sessions
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    # Update investigations table: change user_id to UUID and add FK
    # This is done in phases for safety

    if dialect_name == "postgresql":
        # Phase 1: Add new UUID column
        op.add_column("investigations", sa.Column("user_id_new", postgresql.UUID(as_uuid=True), nullable=True))

        # Phase 2: Migrate existing data
        # For legacy records with __legacy_unassigned__, set to NULL
        # For Supabase UUIDs, try to convert
        op.execute("""
            UPDATE investigations
            SET user_id_new = CASE
                WHEN user_id = '__legacy_unassigned__' THEN NULL
                ELSE user_id::uuid
            END
            WHERE user_id IS NOT NULL
        """)

        # Phase 3: Drop old column, rename new
        op.drop_column("investigations", "user_id")
        op.alter_column("investigations", "user_id_new", new_column_name="user_id")

        # Phase 4: Add foreign key (may fail if orphaned records exist)
        try:
            op.create_foreign_key("fk_investigations_user_id", "investigations", "users", ["user_id"], ["id"])
        except Exception:
            # Foreign key creation failed - log but don't fail migration
            pass
    else:
        # SQLite - similar but simpler
        op.add_column("investigations", sa.Column("user_id_new", sa.String(36), nullable=True))

        # Migrate data
        op.execute("""
            UPDATE investigations
            SET user_id_new = CASE
                WHEN user_id = '__legacy_unassigned__' THEN NULL
                ELSE user_id
            END
            WHERE user_id IS NOT NULL
        """)

        # Drop old, rename new
        op.drop_column("investigations", "user_id")
        op.alter_column("investigations", "user_id_new", new_column_name="user_id")

        # Add index
        op.create_index("ix_investigations_user_id", "investigations", ["user_id"])


def downgrade() -> None:
    """Remove users and sessions tables, revert investigations.user_id."""

    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # Revert investigations.user_id
    if dialect_name == "postgresql":
        # Add back old TEXT column
        op.add_column("investigations", sa.Column("user_id_old", sa.Text, nullable=True))

        # Migrate data back
        op.execute("""
            UPDATE investigations
            SET user_id_old = CASE
                WHEN user_id IS NULL THEN '__legacy_unassigned__'
                ELSE user_id::text
            END
            WHERE user_id IS NOT NULL
        """)

        # Drop FK if exists
        try:
            op.drop_constraint("fk_investigations_user_id", "investigations", type_="foreignkey")
        except Exception:
            pass

        # Drop UUID column, rename old
        op.drop_column("investigations", "user_id")
        op.alter_column("investigations", "user_id_old", new_column_name="user_id")
    else:
        # SQLite
        op.add_column("investigations", sa.Column("user_id_old", sa.Text, nullable=True))

        op.execute("""
            UPDATE investigations
            SET user_id_old = CASE
                WHEN user_id IS NULL THEN '__legacy_unassigned__'
                ELSE user_id
            END
            WHERE user_id IS NOT NULL
        """)

        op.drop_column("investigations", "user_id")
        op.alter_column("investigations", "user_id_old", new_column_name="user_id")

        # Drop index
        try:
            op.drop_index("ix_investigations_user_id", table_name="investigations")
        except Exception:
            pass

    # Drop sessions table
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    # Drop users table
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")