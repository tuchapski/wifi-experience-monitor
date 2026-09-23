from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class _OpenOutage:
    started_at: datetime
    last_failed_at: datetime
    failure_count: int = 1


@dataclass(slots=True)
class _TargetState:
    identity: str
    name: str
    kind: str
    target: str
    port: int | None
    passed: int = 0
    failed: int = 0
    errors: int = 0
    outages: list[dict[str, object]] = field(default_factory=list)
    open_outage: _OpenOutage | None = None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _target_identity(name: str, kind: str, target: str, port: int | None) -> str:
    return json.dumps([name, kind, target, port], ensure_ascii=False, separators=(",", ":"))


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _outage_payload(
    outage: _OpenOutage,
    *,
    ended_at: datetime | None,
    duration_end: datetime,
) -> dict[str, object]:
    duration = max(0.0, (_utc(duration_end) - outage.started_at).total_seconds())
    return {
        "started_at": outage.started_at.isoformat(),
        "last_failed_at": outage.last_failed_at.isoformat(),
        "ended_at": ended_at.isoformat() if ended_at is not None else None,
        "duration_seconds": round(duration, 3),
        "failure_count": outage.failure_count,
        "recovered": ended_at is not None,
    }


def summarize_application_availability(
    samples: list[tuple[datetime, dict[str, object]]],
    *,
    window_end: datetime,
) -> dict[str, object]:
    """Summarize fresh application-target executions and observation-bounded outages."""

    states: dict[str, _TargetState] = {}

    for timestamp, payload in sorted(samples, key=lambda item: _utc(item[0])):
        observed_at = _utc(timestamp)
        connectivity = payload.get("connectivity")
        if not isinstance(connectivity, dict):
            continue
        targets = connectivity.get("application_targets")
        if not isinstance(targets, dict):
            continue

        for metric in targets.values():
            if not isinstance(metric, dict) or metric.get("fresh") is False:
                continue
            status = metric.get("status")
            if status not in {"passed", "failed", "error"}:
                continue

            name = _text(metric.get("name"))
            kind = _text(metric.get("kind"))
            target = _text(metric.get("target"))
            if name is None or kind is None or target is None:
                continue

            raw_port = metric.get("port")
            port = (
                raw_port if isinstance(raw_port, int) and not isinstance(raw_port, bool) else None
            )
            identity = _target_identity(name, kind, target, port)
            state = states.setdefault(
                identity,
                _TargetState(
                    identity=identity,
                    name=name,
                    kind=kind,
                    target=target,
                    port=port,
                ),
            )

            if status == "passed":
                state.passed += 1
                if state.open_outage is not None:
                    state.outages.append(
                        _outage_payload(
                            state.open_outage,
                            ended_at=observed_at,
                            duration_end=observed_at,
                        )
                    )
                    state.open_outage = None
            elif status == "failed":
                state.failed += 1
                if state.open_outage is None:
                    state.open_outage = _OpenOutage(
                        started_at=observed_at,
                        last_failed_at=observed_at,
                    )
                else:
                    state.open_outage.last_failed_at = observed_at
                    state.open_outage.failure_count += 1
            else:
                state.errors += 1

    normalized_end = _utc(window_end)
    targets_summary: list[dict[str, object]] = []

    for state in sorted(
        states.values(),
        key=lambda item: (item.name.casefold(), item.kind, item.target, item.port or -1),
    ):
        outages = list(state.outages)
        if state.open_outage is not None:
            outages.append(
                _outage_payload(
                    state.open_outage,
                    ended_at=None,
                    duration_end=max(normalized_end, state.open_outage.started_at),
                )
            )

        measurable = state.passed + state.failed
        durations = [
            duration
            for outage in outages
            if (duration := _numeric(outage.get("duration_seconds"))) is not None
        ]
        targets_summary.append(
            {
                "identity": state.identity,
                "name": state.name,
                "kind": state.kind,
                "target": state.target,
                "port": state.port,
                "attempt_count": measurable + state.errors,
                "measurable_count": measurable,
                "success_count": state.passed,
                "failure_count": state.failed,
                "measurement_error_count": state.errors,
                "availability_percent": (
                    round(state.passed * 100.0 / measurable, 3) if measurable else None
                ),
                "outage_count": len(outages),
                "open_outage": state.open_outage is not None,
                "observed_outage_seconds": round(sum(durations), 3),
                "longest_observed_outage_seconds": max(durations) if durations else None,
                "outages": outages,
            }
        )

    return {
        "target_count": len(targets_summary),
        "targets": targets_summary,
    }
