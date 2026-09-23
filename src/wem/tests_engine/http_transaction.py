from dataclasses import dataclass
from urllib.parse import urlsplit

from wem.collectors.command import run_command

_TIMING_PREFIX = "__WEM_HTTP_TIMING__:"
_WRITE_OUT = (
    _TIMING_PREFIX + "%{http_code}|%{time_namelookup}|%{time_connect}|%{time_appconnect}|"
    "%{time_starttransfer}|%{time_total}"
)


@dataclass(slots=True)
class HttpTransactionResult:
    status: str
    reason: str
    status_code: int | None
    dns_ms: float | None
    tcp_connect_ms: float | None
    tls_handshake_ms: float | None
    ttfb_ms: float | None
    total_ms: float | None


def _milliseconds(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return round(seconds * 1000, 3)


def _parse_timings(
    output: str,
    *,
    scheme: str,
) -> tuple[int | None, float | None, float | None, float | None, float | None, float | None]:
    line = next(
        (item for item in reversed(output.splitlines()) if item.startswith(_TIMING_PREFIX)),
        "",
    )
    if not line:
        return (None, None, None, None, None, None)

    fields = line.removeprefix(_TIMING_PREFIX).split("|")
    if len(fields) != 6:
        return (None, None, None, None, None, None)

    try:
        status_code = int(fields[0])
    except ValueError:
        status_code = 0
    return (
        status_code if status_code > 0 else None,
        _milliseconds(fields[1]),
        _milliseconds(fields[2]),
        _milliseconds(fields[3]) if scheme == "https" else None,
        _milliseconds(fields[4]),
        _milliseconds(fields[5]),
    )


def probe_http_transaction(url: str, timeout_seconds: float) -> HttpTransactionResult:
    scheme = urlsplit(url).scheme.lower()
    result = run_command(
        [
            "curl",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--max-time",
            f"{timeout_seconds:g}",
            "--user-agent",
            "wifi-experience-monitor/0.1",
            "--write-out",
            _WRITE_OUT,
            url,
        ],
        timeout=timeout_seconds + 1.0,
    )
    status_code, dns_ms, tcp_ms, tls_ms, ttfb_ms, total_ms = _parse_timings(
        result.stdout,
        scheme=scheme,
    )

    if result.returncode in {124, 127}:
        detail = result.stderr or f"curl execution failed with status {result.returncode}"
        return HttpTransactionResult(
            status="error",
            reason=f"HTTP collection error: {detail}",
            status_code=status_code,
            dns_ms=dns_ms,
            tcp_connect_ms=tcp_ms,
            tls_handshake_ms=tls_ms,
            ttfb_ms=ttfb_ms,
            total_ms=total_ms,
        )

    if result.returncode != 0:
        detail = result.stderr or f"curl exited with status {result.returncode}"
        return HttpTransactionResult(
            status="failed",
            reason=f"HTTP transaction failed: {detail}",
            status_code=status_code,
            dns_ms=dns_ms,
            tcp_connect_ms=tcp_ms,
            tls_handshake_ms=tls_ms,
            ttfb_ms=ttfb_ms,
            total_ms=total_ms,
        )

    if status_code is None:
        return HttpTransactionResult(
            status="error",
            reason="HTTP collection error: curl returned no HTTP status code.",
            status_code=None,
            dns_ms=dns_ms,
            tcp_connect_ms=tcp_ms,
            tls_handshake_ms=tls_ms,
            ttfb_ms=ttfb_ms,
            total_ms=total_ms,
        )

    passed = 200 <= status_code < 400
    return HttpTransactionResult(
        status="passed" if passed else "failed",
        reason=f"HTTP response: {status_code}.",
        status_code=status_code,
        dns_ms=dns_ms,
        tcp_connect_ms=tcp_ms,
        tls_handshake_ms=tls_ms,
        ttfb_ms=ttfb_ms,
        total_ms=total_ms,
    )
