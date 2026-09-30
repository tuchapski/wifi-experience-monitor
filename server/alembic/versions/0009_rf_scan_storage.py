"""Store rolling RF neighborhood scans and BSS observations.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_rf_scans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("scan_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interface", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("bss_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "scan_id", name="uq_agent_rf_scan"),
        sa.UniqueConstraint("agent_id", "sequence", name="uq_agent_rf_scan_sequence"),
    )
    op.create_index(
        "ix_agent_rf_scans_agent_observed",
        "agent_rf_scans",
        ["agent_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "agent_rf_bss_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rf_scan_id", sa.BigInteger(), nullable=False),
        sa.Column("bssid", sa.String(length=32), nullable=False),
        sa.Column("ssid", sa.String(length=128), nullable=True),
        sa.Column("frequency_mhz", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=True),
        sa.Column("band", sa.String(length=16), nullable=False),
        sa.Column("rssi_dbm", sa.Float(), nullable=True),
        sa.Column("associated", sa.Boolean(), nullable=False),
        sa.Column("channel_width_mhz", sa.Integer(), nullable=True),
        sa.Column("beacon_interval_tu", sa.Integer(), nullable=True),
        sa.Column("capability", sa.Text(), nullable=True),
        sa.Column("privacy", sa.Boolean(), nullable=False),
        sa.Column(
            "security",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "phy_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("bss_load_station_count", sa.Integer(), nullable=True),
        sa.Column(
            "bss_load_channel_utilization_raw",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("last_seen_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "bss_load_channel_utilization_raw IS NULL "
            "OR (bss_load_channel_utilization_raw >= 0 "
            "AND bss_load_channel_utilization_raw <= 255)",
            name="ck_agent_rf_bss_load_utilization",
        ),
        sa.ForeignKeyConstraint(
            ["rf_scan_id"],
            ["agent_rf_scans.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rf_scan_id",
            "bssid",
            name="uq_agent_rf_bss_scan_bssid",
        ),
    )
    op.create_index(
        "ix_agent_rf_bss_observations_rf_scan_id",
        "agent_rf_bss_observations",
        ["rf_scan_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_rf_bss_bssid",
        "agent_rf_bss_observations",
        ["bssid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_rf_bss_bssid", table_name="agent_rf_bss_observations")
    op.drop_index(
        "ix_agent_rf_bss_observations_rf_scan_id",
        table_name="agent_rf_bss_observations",
    )
    op.drop_table("agent_rf_bss_observations")
    op.drop_index("ix_agent_rf_scans_agent_observed", table_name="agent_rf_scans")
    op.drop_table("agent_rf_scans")
