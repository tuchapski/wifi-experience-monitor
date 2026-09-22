import math
from dataclasses import dataclass, field

_SERVICES = ("gateway", "internet", "dns", "https")

_LATENCY_FIELDS = {
    "gateway": "gateway_latency_avg_ms",
    "internet": "internet_latency_avg_ms",
    "dns": "dns_latency_ms",
    "https": "https_total_time_ms",
}

_PACKET_LOSS_FIELDS = {
    "gateway": "gateway_packet_loss_percent",
    "internet": "internet_packet_loss_percent",
}


@dataclass(slots=True)
class _ServiceState:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)
    losses: list[float] = field(default_factory=list)


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


def summarize_service_executions(
    payloads: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Summarize fresh synthetic-test executions without inventing availability."""

    state = {name: _ServiceState() for name in _SERVICES}

    for payload in payloads:
        connectivity = payload.get("connectivity")
        if not isinstance(connectivity, dict):
            continue
        tests = connectivity.get("tests")
        if not isinstance(tests, dict):
            continue

        for name in _SERVICES:
            outcome = tests.get(name)
            if not isinstance(outcome, dict) or outcome.get("fresh") is False:
                continue
            status = outcome.get("status")
            if status not in {"passed", "failed", "error"}:
                continue

            service = state[name]
            if status == "passed":
                service.passed += 1
                latency = _numeric(connectivity.get(_LATENCY_FIELDS[name]))
                if latency is not None:
                    service.latencies.append(latency)
            elif status == "failed":
                service.failed += 1
            else:
                service.errors += 1

            loss_field = _PACKET_LOSS_FIELDS.get(name)
            if loss_field is not None and status in {"passed", "failed"}:
                loss = _numeric(connectivity.get(loss_field))
                if loss is not None:
                    service.losses.append(loss)

    summary: dict[str, dict[str, object]] = {}
    for name in _SERVICES:
        service = state[name]
        measurable = service.passed + service.failed
        summary[name] = {
            "attempt_count": measurable + service.errors,
            "measurable_count": measurable,
            "success_count": service.passed,
            "failure_count": service.failed,
            "measurement_error_count": service.errors,
            "availability_percent": (
                round(service.passed * 100.0 / measurable, 3) if measurable else None
            ),
            "latency_ms": _aggregate(service.latencies),
            "packet_loss_percent": _aggregate(service.losses),
        }
    return summary
