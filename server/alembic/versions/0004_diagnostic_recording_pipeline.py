"""Add diagnostic recording command and dataset tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_commands",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("command_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'acked', 'failed')",
            name="ck_agent_commands_status",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_commands_agent_id", "agent_commands", ["agent_id"])
    op.create_index(
        "ix_agent_commands_agent_status",
        "agent_commands",
        ["agent_id", "status"],
    )

    op.create_table(
        "recording_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recording_id", sa.String(length=40), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("metric_count", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["diagnostic_recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_id", "batch_id", name="uq_recording_batch"),
        sa.UniqueConstraint("recording_id", "sequence", name="uq_recording_sequence"),
    )
    op.create_index(
        "ix_recording_batches_recording_received",
        "recording_batches",
        ["recording_id", "received_at"],
    )

    op.create_table(
        "recording_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recording_id", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["diagnostic_recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recording_metrics_recording_observed",
        "recording_metrics",
        ["recording_id", "observed_at"],
    )
    op.create_index(
        "ix_recording_metrics_recording_metric_observed",
        "recording_metrics",
        ["recording_id", "metric", "observed_at"],
    )

    op.create_table(
        "recording_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recording_id", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["diagnostic_recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recording_events_event_type", "recording_events", ["event_type"])
    op.create_index(
        "ix_recording_events_recording_observed",
        "recording_events",
        ["recording_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recording_events_recording_observed", table_name="recording_events")
    op.drop_index("ix_recording_events_event_type", table_name="recording_events")
    op.drop_table("recording_events")
    op.drop_index(
        "ix_recording_metrics_recording_metric_observed",
        table_name="recording_metrics",
    )
    op.drop_index("ix_recording_metrics_recording_observed", table_name="recording_metrics")
    op.drop_table("recording_metrics")
    op.drop_index("ix_recording_batches_recording_received", table_name="recording_batches")
    op.drop_table("recording_batches")
    op.drop_index("ix_agent_commands_agent_status", table_name="agent_commands")
    op.drop_index("ix_agent_commands_agent_id", table_name="agent_commands")
    op.drop_table("agent_commands")
