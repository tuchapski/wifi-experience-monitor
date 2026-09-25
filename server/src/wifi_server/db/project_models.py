"""Persist diagnostic projects, execution runs, and recording membership."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from wifi_server.db.base import Base


class DiagnosticProject(Base):
    __tablename__ = "diagnostic_projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    site: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectAgent(Base):
    __tablename__ = "diagnostic_project_agents"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_projects.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), primary_key=True
    )
    location: Mapped[str | None] = mapped_column(String(255))


class ProjectRun(Base):
    __tablename__ = "diagnostic_project_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectRunRecording(Base):
    __tablename__ = "diagnostic_project_run_recordings"
    __table_args__ = (UniqueConstraint("recording_id", name="uq_diagnostic_project_run_recording"),)

    run_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_project_runs.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), primary_key=True
    )
    recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("diagnostic_recordings.id", ondelete="SET NULL"), nullable=True
    )
