"""Add diagnostic projects, selected Agents, and grouped recording runs.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_projects",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("site", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "diagnostic_project_agents",
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["diagnostic_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id", "agent_id"),
    )
    op.create_table(
        "diagnostic_project_runs",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["diagnostic_projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_diagnostic_project_runs_project_id", "diagnostic_project_runs", ["project_id"]
    )
    op.create_table(
        "diagnostic_project_run_recordings",
        sa.Column("run_id", sa.String(length=40), nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("recording_id", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["diagnostic_project_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recording_id"], ["diagnostic_recordings.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("run_id", "agent_id"),
        sa.UniqueConstraint("recording_id", name="uq_diagnostic_project_run_recording"),
    )


def downgrade() -> None:
    op.drop_table("diagnostic_project_run_recordings")
    op.drop_index("ix_diagnostic_project_runs_project_id", table_name="diagnostic_project_runs")
    op.drop_table("diagnostic_project_runs")
    op.drop_table("diagnostic_project_agents")
    op.drop_table("diagnostic_projects")
