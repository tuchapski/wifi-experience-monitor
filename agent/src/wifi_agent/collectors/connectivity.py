"""Synthetic network probes emitted as regular Agent observations."""

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from wifi_agent.collectors.command import run_command
from wifi_agent.core import Observation, ObservationKind

_TIMING_PREFIX = "__WEM_HTTP_TIMING__:"
_HTTP_WRITE_OUT = (
    _TIMING_PREFIX + "%{http_code}|%{time_namelookup}|%{time_connect}|%{time_appconnect}|"
    "%{time_starttransfer}|%{time_total}"
)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    observations: list[Observation]
    errors: list[str]


def _labels(interface: str, target: str) -> dict[str, str]:
    return {"interface": interface, "target": target}


def _state(
    metric: str,
    value: bool | int,
    observed_at: datetime,
    labels: dict[str, str],
) -> Observation:
    return Observation(
        source="synthetic",
        kind=ObservationKind.STATE,
        metric=metric,
        value=value,
        observed_at=observed_at,
        labels=labels,
    )


def _gauge(
    metric: str,
    value: float,
    unit: str,
    observed_at: datetime,
    labels: dict[str, str],
) -> Observation:
    return Observation(
        source="synthetic",
        kind=ObservationKind.GAUGE,
        metric=metric,
        value=round(value, 3),
        unit=unit,
        observed_at=observed_at,
        labels=labels,
    )


def probe_ping(
    name: str,
    target: str,
    interface: str,
    timeout_seconds: float,
) -> ProbeResult:
    """Measure ICMP reachability, loss, latency and jitter for one target."""
    result = run_command(
        [
            "ping",
            "-I",
            interface,
            "-c",
            "4",
            "-i",
            "0.2",
            "-W",
            "2",
            target,
        ],
        timeout=timeout_seconds,
    )
    observed_at = datetime.now(UTC)
    labels = _labels(interface, target)
    loss_match = re.search(r"([\d.]+)% packet loss", result.stdout)
    if loss_match is None or result.returncode not in {0, 1}:
        detail = result.stderr or "No valid ping statistics were returned."
        return ProbeResult([], [f"{name} ping collection failed: {detail}"])

    packet_loss = float(loss_match.group(1))
    observations = [
        _state(f"network.{name}_reachable", packet_loss < 100.0, observed_at, labels),
        _gauge(
            f"network.{name}_packet_loss_percent",
            packet_loss,
            "%",
            observed_at,
            labels,
        ),
    ]
    latency_match = re.search(
        r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms",
        result.stdout,
    )
    if latency_match is not None:
        minimum, average, maximum, jitter = (float(item) for item in latency_match.groups())
        observations.extend(
            [
                _gauge(f"network.{name}_latency_min_ms", minimum, "ms", observed_at, labels),
                _gauge(f"network.{name}_latency_ms", average, "ms", observed_at, labels),
                _gauge(f"network.{name}_latency_max_ms", maximum, "ms", observed_at, labels),
                _gauge(f"network.{name}_jitter_ms", jitter, "ms", observed_at, labels),
            ]
        )
    return ProbeResult(observations, [])


def probe_dns(
    query: str,
    interface: str,
    timeout_seconds: float,
) -> ProbeResult:
    """Measure system-resolver completion time without treating DNS failure as collector failure."""
    started = time.perf_counter()
    result = run_command(["getent", "ahostsv4", query], timeout=timeout_seconds)
    elapsed_ms = (time.perf_counter() - started) * 1000
    observed_at = datetime.now(UTC)
    labels = _labels(interface, query)
    success = result.returncode == 0 and bool(result.stdout.strip())
    observations = [_state("network.dns_success", success, observed_at, labels)]
    if success:
        observations.append(_gauge("network.dns_latency_ms", elapsed_ms, "ms", observed_at, labels))
    errors = []
    if result.returncode in {124, 127}:
        detail = result.stderr or f"getent exited with status {result.returncode}"
        errors.append(f"DNS collection failed: {detail}")
    return ProbeResult(observations, errors)


def _milliseconds(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return round(seconds * 1000, 3)


def probe_https(
    url: str,
    interface: str,
    timeout_seconds: float,
    source_address: str | None = None,
) -> ProbeResult:
    """Measure cumulative HTTPS transaction milestones using curl."""
    command = [
        "curl",
        "--ipv4",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--max-time",
        f"{timeout_seconds:g}",
    ]
    if source_address:
        command.extend(["--interface", source_address])
    command.extend(
        [
            "--user-agent",
            "wifi-experience-monitor/0.1",
            "--write-out",
            _HTTP_WRITE_OUT,
            url,
        ]
    )
    result = run_command(command, timeout=timeout_seconds + 1.0)
    observed_at = datetime.now(UTC)
    labels = _labels(interface, url)
    timing_line = next(
        (line for line in reversed(result.stdout.splitlines()) if line.startswith(_TIMING_PREFIX)),
        "",
    )
    fields = timing_line.removeprefix(_TIMING_PREFIX).split("|") if timing_line else []
    status_code: int | None = None
    timings: list[float | None] = [None] * 5
    if len(fields) == 6:
        try:
            parsed_status = int(fields[0])
        except ValueError:
            parsed_status = 0
        status_code = parsed_status if parsed_status > 0 else None
        timings = [_milliseconds(value) for value in fields[1:]]

    success = result.returncode == 0 and status_code is not None and 200 <= status_code < 400
    observations = [_state("network.https_success", success, observed_at, labels)]
    if status_code is not None:
        observations.append(_state("network.https_status_code", status_code, observed_at, labels))
    metric_names = (
        "network.https_dns_ms",
        "network.https_tcp_connect_ms",
        "network.https_tls_handshake_ms",
        "network.https_ttfb_ms",
    )
    observations.extend(
        _gauge(metric, value, "ms", observed_at, labels)
        for metric, value in zip(metric_names, timings[:4], strict=True)
        if value is not None
    )
    total_ms = timings[4]
    transaction_completed = result.returncode == 0 and status_code is not None
    if total_ms is not None:
        metric = (
            "network.https_total_ms"
            if transaction_completed
            else "network.https_failure_elapsed_ms"
        )
        observations.append(_gauge(metric, total_ms, "ms", observed_at, labels))
    errors = []
    if result.returncode in {124, 127}:
        detail = result.stderr or f"curl exited with status {result.returncode}"
        errors.append(f"HTTPS collection failed: {detail}")
    return ProbeResult(observations, errors)
