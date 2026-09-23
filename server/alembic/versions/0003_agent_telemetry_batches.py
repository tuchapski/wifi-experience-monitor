"""Add telemetry batch receipt tracking.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_telemetry_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "batch_id", name="uq_agent_telemetry_batch"),
        sa.UniqueConstraint("agent_id", "sequence", name="uq_agent_telemetry_sequence"),
    )
    op.create_index(
        "ix_agent_telemetry_batches_agent_received",
        "agent_telemetry_batches",
        ["agent_id", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_telemetry_batches_agent_received",
        table_name="agent_telemetry_batches",
    )
    op.drop_table("agent_telemetry_batches")
