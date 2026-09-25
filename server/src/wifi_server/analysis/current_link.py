"""Explainable, per-snapshot Wi-Fi link score. No active network tests are implied."""

from math import isfinite
from typing import Any

VERSION = "wifi-link-v1"
METRICS = (
    (
        "rssi_dbm",
        "RSSI",
        "dBm",
        60,
        ((-90.0, 0.0), (-82.0, 40.0), (-75.0, 70.0), (-67.0, 100.0)),
    ),
    (
        "tx_retries_per_100_packets",
        "TX retries",
        "per 100 packets",
        25,
        ((0.0, 100.0), (10.0, 100.0), (20.0, 70.0), (50.0, 20.0), (100.0, 0.0)),
    ),
    (
        "tx_failed_percent",
        "TX failures",
        "%",
        15,
        ((0.0, 100.0), (1.0, 85.0), (5.0, 20.0), (10.0, 0.0)),
    ),
)


def _reading(metric: str, value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not isfinite(number):
        return None
    if metric == "rssi_dbm" and not -120 <= number <= 0:
        return None
    if metric == "tx_retries_per_100_packets" and number < 0:
        return None
    if metric == "tx_failed_percent" and not 0 <= number <= 100:
        return None
    return number


def _interpolate(value: float, anchors: tuple[tuple[float, float], ...]) -> float:
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (low, low_score), (high, high_score) in zip(anchors, anchors[1:], strict=False):
        if value <= high:
            return low_score + (value - low) * (high_score - low_score) / (high - low)
    return anchors[-1][1]


def score_link(wifi: dict[str, Any], collector_errors: list[str]) -> dict[str, Any]:
    connected = wifi.get("connected")
    components: list[dict[str, Any]] = []
    available_weight = 0
    weighted_score = 0.0
    for key, label, unit, weight, anchors in METRICS:
        reading = _reading(key, wifi.get(key)) if connected is True else None
        points = _interpolate(reading, anchors) if reading is not None else None
        if points is not None:
            available_weight += weight
            weighted_score += points * weight
        components.append(
            {
                "metric": key,
                "label": label,
                "unit": unit,
                "weight_percent": weight,
                "reading": reading,
                "score": round(points, 1) if points is not None else None,
            }
        )

    limitations: list[str] = []
    if connected is False:
        status = "disconnected"
        value: float | None = 0.0
        limitations.append("The Agent observed a Wi-Fi disconnection.")
    elif connected is not True:
        status = "unavailable"
        value = None
        limitations.append("Wi-Fi association could not be confirmed.")
    elif components[0]["score"] is None:
        status = "unavailable"
        value = None
        limitations.append("An associated RSSI reading is required for a link score.")
    else:
        value = round(weighted_score / available_weight, 1)
        status = "measured" if available_weight == 100 else "provisional"
        if available_weight < 100:
            limitations.append("Traffic counters did not provide all comparable interval metrics.")

    if collector_errors:
        limitations.append("One or more collectors reported an error in this cycle.")
        if status == "measured":
            status = "provisional"

    limitations.append("This score covers the Wi-Fi link only, not DNS, Internet or applications.")
    return {
        "version": VERSION,
        "value": value,
        "status": status,
        "coverage_percent": available_weight,
        "components": components,
        "limitations": limitations,
    }
