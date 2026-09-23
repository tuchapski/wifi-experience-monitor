"""Initial agent/server schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("agent_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("os_name", sa.String(length=128), nullable=True),
        sa.Column("os_version", sa.String(length=128), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agents_agent_type", "agents", ["agent_type"])
    op.create_index("ix_agents_last_seen_at", "agents", ["last_seen_at"])
    op.create_index("ix_agents_status", "agents", ["status"])

    op.create_table(
        "agent_capabilities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("capability", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "capability", name="uq_agent_capability"),
    )
    op.create_index("ix_agent_capabilities_agent_id", "agent_capabilities", ["agent_id"])

    op.create_table(
        "agent_current_state",
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wifi_connected", sa.Boolean(), nullable=True),
        sa.Column("interface", sa.String(length=64), nullable=True),
        sa.Column("ssid", sa.String(length=128), nullable=True),
        sa.Column("bssid", sa.String(length=32), nullable=True),
        sa.Column("frequency_mhz", sa.Integer(), nullable=True),
        sa.Column("channel", sa.Integer(), nullable=True),
        sa.Column("channel_width_mhz", sa.Integer(), nullable=True),
        sa.Column("rssi_dbm", sa.Float(), nullable=True),
        sa.Column("snr_db", sa.Float(), nullable=True),
        sa.Column("tx_rate_mbps", sa.Float(), nullable=True),
        sa.Column("rx_rate_mbps", sa.Float(), nullable=True),
        sa.Column("gateway_latency_ms", sa.Float(), nullable=True),
        sa.Column("dns_latency_ms", sa.Float(), nullable=True),
        sa.Column("internet_latency_ms", sa.Float(), nullable=True),
        sa.Column("experience_score", sa.Float(), nullable=True),
        sa.Column("raw_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id"),
    )
    op.create_index(
        "ix_agent_current_state_observed_at",
        "agent_current_state",
        ["observed_at"],
    )

    op.create_table(
        "agent_telemetry",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_telemetry_agent_observed",
        "agent_telemetry",
        ["agent_id", "observed_at"],
    )
    op.create_index(
        "ix_agent_telemetry_agent_metric_observed",
        "agent_telemetry",
        ["agent_id", "metric", "observed_at"],
    )

    op.create_table(
        "agent_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_events_agent_observed",
        "agent_events",
        ["agent_id", "observed_at"],
    )
    op.create_index("ix_agent_events_event_type", "agent_events", ["event_type"])

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=False),
        sa.Column("remote_address", sa.String(length=255), nullable=True),
        sa.Column("disconnect_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_sessions_agent_id", "agent_sessions", ["agent_id"])
    op.create_index("ix_agent_sessions_connected_at", "agent_sessions", ["connected_at"])
    op.create_index(
        "ix_agent_sessions_disconnected_at",
        "agent_sessions",
        ["disconnected_at"],
    )

    op.create_table(
        "diagnostic_recordings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("site", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("metrics_count", sa.BigInteger(), nullable=False),
        sa.Column("events_count", sa.BigInteger(), nullable=False),
        sa.Column("tests_count", sa.BigInteger(), nullable=False),
        sa.Column("artifacts_count", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('created', 'recording', 'stopping', 'completed', 'failed', 'cancelled')",
            name="ck_diagnostic_recordings_status",
        ),
        sa.CheckConstraint(
            "sync_status IN ('pending', 'syncing', 'complete', 'incomplete', 'failed')",
            name="ck_diagnostic_recordings_sync_status",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagnostic_recordings_agent_id", "diagnostic_recordings", ["agent_id"])
    op.create_index(
        "ix_diagnostic_recordings_agent_started",
        "diagnostic_recordings",
        ["agent_id", "started_at"],
    )
    op.create_index("ix_diagnostic_recordings_status", "diagnostic_recordings", ["status"])
    op.create_index(
        "ix_diagnostic_recordings_sync_status",
        "diagnostic_recordings",
        ["sync_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagnostic_recordings_sync_status", table_name="diagnostic_recordings")
    op.drop_index("ix_diagnostic_recordings_status", table_name="diagnostic_recordings")
    op.drop_index("ix_diagnostic_recordings_agent_started", table_name="diagnostic_recordings")
    op.drop_index("ix_diagnostic_recordings_agent_id", table_name="diagnostic_recordings")
    op.drop_table("diagnostic_recordings")

    op.drop_index("ix_agent_sessions_disconnected_at", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_connected_at", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_agent_id", table_name="agent_sessions")
    op.drop_table("agent_sessions")

    op.drop_index("ix_agent_events_event_type", table_name="agent_events")
    op.drop_index("ix_agent_events_agent_observed", table_name="agent_events")
    op.drop_table("agent_events")

    op.drop_index("ix_agent_telemetry_agent_metric_observed", table_name="agent_telemetry")
    op.drop_index("ix_agent_telemetry_agent_observed", table_name="agent_telemetry")
    op.drop_table("agent_telemetry")

    op.drop_index("ix_agent_current_state_observed_at", table_name="agent_current_state")
    op.drop_table("agent_current_state")

    op.drop_index("ix_agent_capabilities_agent_id", table_name="agent_capabilities")
    op.drop_table("agent_capabilities")

    op.drop_index("ix_agents_status", table_name="agents")
    op.drop_index("ix_agents_last_seen_at", table_name="agents")
    op.drop_index("ix_agents_agent_type", table_name="agents")
    op.drop_table("agents")
