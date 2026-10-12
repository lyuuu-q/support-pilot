"""Add LangGraph agent run checkpoint tables.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op
from langgraph.checkpoint.postgres import PostgresSaver

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for statement in PostgresSaver.MIGRATIONS:
        if "CONCURRENTLY" in statement:
            with op.get_context().autocommit_block():
                op.execute(statement)
        else:
            op.execute(statement)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS checkpoint_writes, checkpoint_blobs, "
        "checkpoints, checkpoint_migrations CASCADE"
    )
