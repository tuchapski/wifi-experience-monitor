"""Lightweight, bounded scan timing context; no BSS inventory or causal diagnosis."""

from datetime import timedelta
from math import isfinite

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wifi_server.db.models import AgentRfScan, DiagnosticRecording
from wifi_server.rf_summary_schemas import RecordingRfScanWindow, RecordingRfScanWindows


def get_recording_rf_windows(
    session: Session, recording_id: str, limit: int = 2000
) -> RecordingRfScanWindows:
    if session.get(DiagnosticRecording, recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    scan = AgentRfScan
    total = (
        session.scalar(
            select(func.count()).select_from(scan).where(scan.recording_id == recording_id)
        )
        or 0
    )
    rows = session.execute(
        select(scan.scan_id, scan.interface, scan.observed_at, scan.duration_ms)
        .where(scan.recording_id == recording_id)
        .order_by(scan.observed_at.desc(), scan.id.desc())
        .limit(limit)
    ).all()
    windows = []
    invalid = 0
    for scan_id, interface, ended_at, duration_ms in reversed(rows):
        try:
            if not isfinite(duration_ms) or duration_ms < 0:
                raise ValueError("Invalid duration")
            started_at = ended_at - timedelta(milliseconds=duration_ms)
        except (OverflowError, ValueError, TypeError):
            invalid += 1
            continue
        windows.append(
            RecordingRfScanWindow(
                scan_id=scan_id,
                interface=interface,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )
        )
    return RecordingRfScanWindows(
        total_scans=total,
        loaded_scans=len(rows),
        invalid_windows=invalid,
        truncated=total > len(rows),
        windows=windows,
    )
