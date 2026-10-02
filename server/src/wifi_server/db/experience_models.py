from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wifi_server.db.base import Base


class AgentExperienceMonitor(Base):
    __tablename__ = "agent_experience_monitors"

    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    detector_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
