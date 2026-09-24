"""Add versioned diagnostic recording analyses.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recording_analyses",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("recording_id", sa.String(length=40), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_metrics_count", sa.BigInteger(), nullable=False),
        sa.Column("source_events_count", sa.BigInteger(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('complete', 'failed')",
            name="ck_recording_analyses_status",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["diagnostic_recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recording_analyses_recording_id",
        "recording_analyses",
        ["recording_id"],
    )
    op.create_index(
        "ix_recording_analyses_recording_created",
        "recording_analyses",
        ["recording_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recording_analyses_recording_created",
        table_name="recording_analyses",
    )
    op.drop_index("ix_recording_analyses_recording_id", table_name="recording_analyses")
    op.drop_table("recording_analyses")
