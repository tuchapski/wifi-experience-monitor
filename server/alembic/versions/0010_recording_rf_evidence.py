"""Associate RF scans with diagnostic recordings.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_rf_scans",
        sa.Column("recording_id", sa.String(length=40), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_rf_scans_recording_id",
        "agent_rf_scans",
        "diagnostic_recordings",
        ["recording_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_agent_rf_scans_recording_id",
        "agent_rf_scans",
        ["recording_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_rf_scans_recording_id", table_name="agent_rf_scans")
    op.drop_constraint(
        "fk_agent_rf_scans_recording_id",
        "agent_rf_scans",
        type_="foreignkey",
    )
    op.drop_column("agent_rf_scans", "recording_id")
