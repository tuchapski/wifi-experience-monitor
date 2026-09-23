from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wifi_server.db.base import Base


class AgentCommand(Base):
    __tablename__ = "agent_commands"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'delivered', 'acked', 'failed')",
            name="ck_agent_commands_status",
        ),
        Index("ix_agent_commands_agent_status", "agent_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class RecordingBatch(Base):
    __tablename__ = "recording_batches"
    __table_args__ = (
        UniqueConstraint("recording_id", "batch_id", name="uq_recording_batch"),
        UniqueConstraint("recording_id", "sequence", name="uq_recording_sequence"),
        Index("ix_recording_batches_recording_received", "recording_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metric_count: Mapped[int] = mapped_column(Integer, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecordingMetric(Base):
    __tablename__ = "recording_metrics"
    __table_args__ = (
        Index("ix_recording_metrics_recording_observed", "recording_id", "observed_at"),
        Index(
            "ix_recording_metrics_recording_metric_observed",
            "recording_id",
            "metric",
            "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecordingEvent(Base):
    __tablename__ = "recording_events"
    __table_args__ = (
        Index("ix_recording_events_recording_observed", "recording_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
