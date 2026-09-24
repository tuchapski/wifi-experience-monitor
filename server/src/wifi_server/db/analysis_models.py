from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wifi_server.db.base import Base


class RecordingAnalysis(Base):
    __tablename__ = "recording_analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('complete', 'failed')",
            name="ck_recording_analyses_status",
        ),
        Index(
            "ix_recording_analyses_recording_created",
            "recording_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("diagnostic_recordings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_metrics_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_events_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
