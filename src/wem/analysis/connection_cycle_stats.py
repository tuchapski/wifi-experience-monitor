import math
from collections import Counter

_STAGE_KEYS = (
    "association",
    "authentication",
    "authorization",
    "dhcp",
    "gateway",
    "dns",
    "network_ready",
)


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)


def _aggregate(values: list[float]) -> dict[str, float | int | None]:
    return {
        "avg": round(sum(values) / len(values), 3) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "count": len(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
    }


def summarize_connection_cycles(cycles: list[dict[str, object]]) -> dict[str, object]:
    """Summarize unique connection sessions without turning missing timing into zero."""

    total_times: list[float] = []
    stage_values: dict[str, list[float]] = {key: [] for key in _STAGE_KEYS}
    stage_sources: dict[str, Counter[str]] = {key: Counter() for key in _STAGE_KEYS}
    by_type: Counter[str] = Counter()
    by_state: Counter[str] = Counter()
    by_timing_source: Counter[str] = Counter()

    for cycle in cycles:
        session_type = cycle.get("session_type")
        if isinstance(session_type, str) and session_type:
            by_type[session_type] += 1

        state = cycle.get("state")
        if isinstance(state, str) and state:
            by_state[state] += 1

        timing_source = cycle.get("timing_source")
        if isinstance(timing_source, str) and timing_source:
            by_timing_source[timing_source] += 1

        total_time = _numeric(cycle.get("total_time_ms"))
        if total_time is not None:
            total_times.append(total_time)

        stages = cycle.get("stages")
        if not isinstance(stages, dict):
            continue
        for key in _STAGE_KEYS:
            stage = stages.get(key)
            if not isinstance(stage, dict):
                continue
            elapsed = _numeric(stage.get("elapsed_ms"))
            if elapsed is not None:
                stage_values[key].append(elapsed)
                source = stage.get("source")
                if isinstance(source, str) and source:
                    stage_sources[key][source] += 1

    stages_summary: dict[str, object] = {}
    for key in _STAGE_KEYS:
        stages_summary[key] = {
            **_aggregate(stage_values[key]),
            "sources": dict(sorted(stage_sources[key].items())),
        }

    return {
        "total_cycles": len(cycles),
        "ready_cycles": by_state.get("ready", 0),
        "measurable_cycles": len(total_times),
        "unmeasured_cycles": len(cycles) - len(total_times),
        "by_type": dict(sorted(by_type.items())),
        "by_state": dict(sorted(by_state.items())),
        "by_timing_source": dict(sorted(by_timing_source.items())),
        "total_time_ms": _aggregate(total_times),
        "stages": stages_summary,
    }
