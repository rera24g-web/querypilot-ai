"""Add user_id column for investigation ownership

Revision ID: 20241105_initial_migration
Revises: None
Create Date: 2024-11-05 00:00:00.000000

This migration adds user_id column to the investigations table for
Supabase Auth integration. It handles both SQLite and PostgreSQL schemas.

BACKUP AND ROLLBACK:
- Backup: The column addition is additive only; no data is modified.
- Rollback: Run `alembic downgrade -1` to remove the column.
- Note: ROLLBACK will DELETE existing investigation data with user_id column.

MIGRATION NOTES:
- SQLite: ALTER TABLE ADD COLUMN is supported and safe
- PostgreSQL: Same operation is safe
- Default value for existing records: 'legacy_unassigned' (temporary marker)
- New records must have a valid user_id from Supabase Auth

LEGACY DATA HANDLING:
- Existing records without user_id become unowned after migration
- These records will NOT be accessible to authenticated users
- This is intentional - ownership must be explicit and verified
- Legacy records can be reassigned by admins if needed
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "20241105_initial_migration"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add user_id column and index for investigation ownership."""
    # Get the database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # Add user_id column
    # Using server_default for backward compatibility during migration
    # Legacy records get marker, new records get proper user_id
    if dialect_name == "sqlite":
        # SQLite: Add column with default for existing records
        op.add_column(
            "investigations",
            sa.Column("user_id", sa.String(36), nullable=False, server_default="legacy_unassigned")
        )
    else:
        # PostgreSQL and others: Same approach
        op.add_column(
            "investigations",
            sa.Column("user_id", sa.String(36), nullable=False, server_default="legacy_unassigned")
        )

    # Create index for efficient user-specific queries
    op.create_index("ix_investigations_user_id", "investigations", ["user_id"])


def downgrade() -> None:
    """Remove user_id column and index."""
    # Drop index first
    op.drop_index("ix_investigations_user_id", table_name="investigations")

    # Drop column
    op.drop_column("investigations", "user_id")