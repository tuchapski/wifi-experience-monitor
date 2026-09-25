"""Bounded chart data across the entire recording, preserving sampled extremes."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.recording_models import RecordingMetric
from wifi_server.recording_schemas import RecordingChartPoint, RecordingMetricOverview


@dataclass(frozen=True)
class _Sample:
    observed_at: datetime
    value: float
    id: int


@dataclass
class _Summary:
    count: int = 0
    total: float = 0
    minimum: float | None = None
    maximum: float | None = None
    first: _Sample | None = None
    last: _Sample | None = None
    buckets: dict[int, tuple[_Sample, _Sample]] = field(default_factory=dict)


def _sample_order(sample: _Sample) -> tuple[datetime, int]:
    return sample.observed_at, sample.id


def summarize_metric_rows(
    rows: Iterable[tuple[str, datetime, float, int]],
    metrics: list[str],
    started_at: datetime,
    ended_at: datetime,
    buckets: int,
) -> list[RecordingMetricOverview]:
    """Keep each interval's low and high, plus the first and last observations."""
    span = max((ended_at - started_at).total_seconds(), 1)
    summaries = {metric: _Summary() for metric in metrics}

    for metric, observed_at, value, sample_id in rows:
        summary = summaries[metric]
        sample = _Sample(observed_at, value, sample_id)
        position = min(
            buckets - 1,
            max(0, int((observed_at - started_at).total_seconds() * buckets / span)),
        )
        summary.count += 1
        summary.total += value
        summary.minimum = value if summary.minimum is None else min(summary.minimum, value)
        summary.maximum = value if summary.maximum is None else max(summary.maximum, value)
        if summary.first is None or _sample_order(sample) < _sample_order(summary.first):
            summary.first = sample
        if summary.last is None or _sample_order(sample) > _sample_order(summary.last):
            summary.last = sample
        low, high = summary.buckets.get(position, (sample, sample))
        summary.buckets[position] = (
            sample if value < low.value else low,
            sample if value > high.value else high,
        )

    output: list[RecordingMetricOverview] = []
    for metric, summary in summaries.items():
        retained = {sample.id: sample for pair in summary.buckets.values() for sample in pair}
        for edge in (summary.first, summary.last):
            if edge is not None:
                retained[edge.id] = edge
        points = sorted(retained.values(), key=_sample_order)
        output.append(
            RecordingMetricOverview(
                metric=metric,
                sample_count=summary.count,
                minimum=summary.minimum,
                average=summary.total / summary.count if summary.count else None,
                maximum=summary.maximum,
                points=[
                    RecordingChartPoint(observed_at=sample.observed_at, value=sample.value)
                    for sample in points
                ],
            )
        )
    return output


def get_metric_overviews(
    session: Session,
    recording_id: str,
    metrics: list[str],
    buckets: int,
) -> list[RecordingMetricOverview]:
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    started_at = recording.started_at or recording.created_at
    ended_at = recording.ended_at or datetime.now(UTC)
    statement = (
        select(
            RecordingMetric.metric,
            RecordingMetric.observed_at,
            RecordingMetric.value,
            RecordingMetric.id,
        )
        .where(RecordingMetric.recording_id == recording_id, RecordingMetric.metric.in_(metrics))
        .order_by(RecordingMetric.metric, RecordingMetric.observed_at, RecordingMetric.id)
        .execution_options(yield_per=1000)
    )
    return summarize_metric_rows(session.execute(statement), metrics, started_at, ended_at, buckets)
