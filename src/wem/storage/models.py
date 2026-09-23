from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SnapshotRecord(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        index=True,
    )

    interface: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    ssid: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    bssid: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    signal_dbm: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    signal_avg_dbm: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    gateway_latency_avg_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    gateway_packet_loss_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    internet_latency_avg_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    internet_packet_loss_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    dns_latency_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    https_total_time_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    tx_retries_per_100_packets: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    overall_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    probable_domain: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    collector_errors: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    snapshot_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    domain: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )

    opened_at: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        index=True,
    )


class TestProfileRecord(Base):
    __tablename__ = "test_profiles"
    __table_args__ = (
        Index(
            "uq_test_profiles_single_active",
            text("1"),
            unique=True,
            sqlite_where=text("active_version_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_profile_versions.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)


class TestProfileVersionRecord(Base):
    __tablename__ = "test_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("test_profiles.id"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class MonitoringSessionRecord(Base):
    __tablename__ = "monitoring_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interface: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("test_profiles.id"), nullable=False, index=True
    )
    profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("test_profile_versions.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
