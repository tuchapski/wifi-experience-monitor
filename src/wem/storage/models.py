from datetime import datetime

from sqlalchemy import Float, Integer, String, Text
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
