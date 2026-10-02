"""Persist client-specific policy and bounded incremental detector state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_experience_monitors",
        sa.Column(
            "agent_id",
            sa.String(40),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        sa.Column("detector_state", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_experience_monitors")
