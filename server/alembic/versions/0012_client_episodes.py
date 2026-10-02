"""Persist individual episodes, transitions and recording coverage links."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_experience_episodes",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(40),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("target", sa.Text()),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("detector_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("recurrence_count", sa.Integer(), nullable=False),
        sa.Column("observed_duration_seconds", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_client_episodes_agent_started", "client_experience_episodes", ["agent_id", "started_at"]
    )
    op.create_index(
        "uq_client_episode_open_scope",
        "client_experience_episodes",
        ["agent_id", "scope_key"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_table(
        "client_episode_events",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(40),
            sa.ForeignKey("client_experience_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_episode_events_episode_time", "client_episode_events", ["episode_id", "observed_at"]
    )
    op.create_table(
        "client_episode_captures",
        sa.Column(
            "episode_id",
            sa.String(40),
            sa.ForeignKey("client_experience_episodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "recording_id",
            sa.String(40),
            sa.ForeignKey("diagnostic_recordings.id", ondelete="SET NULL"),
        ),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_client_episode_captures_recording_id", "client_episode_captures", ["recording_id"]
    )


def downgrade() -> None:
    op.drop_table("client_episode_captures")
    op.drop_table("client_episode_events")
    op.drop_table("client_experience_episodes")
