"""Add ticket queue pagination indexes.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_tickets_created_at_id",
        "tickets",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_tickets_status_created_at_id",
        "tickets",
        ["status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_status_created_at_id", table_name="tickets")
    op.drop_index("ix_tickets_created_at_id", table_name="tickets")
