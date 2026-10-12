"""Extend agent run statuses for checkpoint recovery.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_agent_runs_valid_status"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_status"),
        "agent_runs",
        "status IN ('running', 'interrupted', 'answered', 'needs_clarification', "
        "'needs_confirmation', 'escalated', 'refused', 'cancelled', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_agent_runs_valid_status"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_status"),
        "agent_runs",
        "status IN ('running', 'answered', 'needs_clarification', "
        "'needs_confirmation', 'escalated', 'refused', 'cancelled', 'failed')",
    )
