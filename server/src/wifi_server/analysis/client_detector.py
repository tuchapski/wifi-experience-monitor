"""Bounded incremental rules. Repeated snapshots never advance a streak or a reference."""

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from statistics import median

from wifi_server.experience_schemas import ClientExperienceResponse
from wifi_server.monitor_schemas import ExperienceProfile
from wifi_server.schemas import AgentCurrentStateResponse

DETECTOR_VERSION = "client-detector-v1"
MAX_REFERENCES = 32
MAX_REFERENCE_SAMPLES = 120


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def band(frequency: int | None) -> str:
    if frequency is None:
        return "unknown"
    return "2.4ghz" if frequency < 3000 else "5ghz" if frequency < 5925 else "6ghz"


def _reference(samples: list[list], observed_at: str) -> dict:
    values = sorted(float(item[1]) for item in samples)
    center = median(values)
    mad = median(abs(value - center) for value in values)
    p95 = values[max(0, int(len(values) * 0.95 + 0.999) - 1)]
    return {
        "status": "ready",
        "samples": len(values),
        "median": center,
        "mad": mad,
        "p95": p95,
        "established_at": observed_at,
    }


def _unknown(entry: dict, reason: str) -> None:
    if entry.get("status") != "unknown":
        entry["previous_status"] = entry.get("status")
    entry.update(
        status="unknown",
        reason=reason,
        evidence_gap=True,
        consecutive_samples=0,
        bad_since=None,
        good_since=None,
        last_bad=None,
    )


def _advance(
    entry: dict,
    *,
    bad: bool,
    immediate: bool,
    time: datetime,
    profile: ExperienceProfile,
    gap: bool,
) -> None:
    previous = entry.get("status", "unknown")
    confirmed = entry.get("confirmed", False)
    if gap:
        entry.update(
            bad_since=None, good_since=None, consecutive_samples=0, last_bad=None, evidence_gap=True
        )
    if bad:
        entry["good_since"] = None
        if not entry.get("bad_since"):
            if not confirmed:
                entry.update(since=time.isoformat(), observed_duration_seconds=0)
            entry["bad_since"] = time.isoformat()
            entry["consecutive_samples"] = 0
        entry["consecutive_samples"] += 1
        if entry.get("last_bad"):
            entry["observed_duration_seconds"] = round(
                entry.get("observed_duration_seconds", 0)
                + (time - timestamp(entry["last_bad"])).total_seconds(),
                3,
            )
        entry["last_bad"] = time.isoformat()
        span = (time - timestamp(entry["bad_since"])).total_seconds()
        if (
            confirmed
            or immediate
            or (
                entry["consecutive_samples"] >= profile.minimum_samples
                and span >= profile.confirm_seconds
            )
        ):
            entry["confirmed"] = True
            entry["status"] = "active"
            entry["since"] = entry.get("since") or entry["bad_since"]
        else:
            entry["status"] = "candidate"
            entry["since"] = entry["bad_since"]
    else:
        entry.update(bad_since=None, last_bad=None)
        if confirmed:
            if not entry.get("good_since"):
                entry["good_since"] = time.isoformat()
                entry["consecutive_samples"] = 0
            entry["consecutive_samples"] += 1
            span = (time - timestamp(entry["good_since"])).total_seconds()
            if entry["consecutive_samples"] >= 2 and span >= profile.recover_seconds:
                entry.update(status="recovered", confirmed=False, good_since=None)
            else:
                entry["status"] = "recovering"
        else:
            entry.update(
                status="normal",
                consecutive_samples=0,
                good_since=None,
                since=None,
                observed_duration_seconds=0,
                evidence_gap=False,
            )
    if previous != entry["status"]:
        entry["previous_status"] = previous


def consume_snapshot(
    previous: dict,
    state: AgentCurrentStateResponse,
    experience: ClientExperienceResponse,
    profile: ExperienceProfile,
    version: str,
) -> dict:
    """Consume only new, valid observations with the actually applied policy and context."""
    result = deepcopy(previous) if previous.get("version") == DETECTOR_VERSION else {}
    result["version"] = DETECTOR_VERSION
    rules = result.setdefault("rules", {})
    references = result.setdefault("references", {})
    for domain in experience.domains:
        outcome = domain.measurements[0]
        definitions = [(outcome, None)]
        if domain.domain != "wifi_rf":
            objectives = getattr(profile, domain.domain)
            for item in domain.measurements[1:]:
                limit = (
                    objectives.latency_ms
                    if item.metric.endswith(("_latency_ms", "_total_ms"))
                    else objectives.packet_loss_percent
                    if item.metric.endswith("_packet_loss_percent")
                    else objectives.jitter_ms
                    if item.metric.endswith("_jitter_ms")
                    else objectives.ttfb_ms
                    if item.metric.endswith("_ttfb_ms")
                    else None
                )
                relative = item.metric.endswith(
                    ("_latency_ms", "_total_ms", "_jitter_ms", "_ttfb_ms")
                )
                primary = item.metric.endswith(("_latency_ms", "_total_ms"))
                known = item.metric in rules
                if limit is not None or (relative and (primary or known or item.value is not None)):
                    definitions.append((item, limit))
        for item, objective in definitions:
            availability = item is outcome
            entry = rules.setdefault(item.metric, {"status": "unknown"})
            meta = state.measurement_metadata.get(item.metric)
            context = {
                "interface": state.wifi.interface or "unknown",
                "location": profile.location,
                "ssid": state.wifi.ssid or "unknown",
                "band": band(state.wifi.frequency_mhz),
                "target": item.target or "",
                "profile": version,
            }
            # Disconnection has no SSID. Association availability survives its disappearance.
            if domain.domain == "wifi_rf":
                context.update(ssid="association", band="association")
            entry.update(
                rule_id=item.metric,
                domain=domain.domain,
                metric=item.metric,
                label=item.label,
                unit=item.unit,
                target=item.target,
                objective=objective,
            )
            domain_available = domain.status in {"observed_ok", "failure", "degraded"}
            context_valid = domain.domain == "wifi_rf" or bool(
                meta
                and meta.labels.get("ssid") == state.wifi.ssid
                and meta.labels.get("band") == context["band"]
                and state.wifi.connected is True
                and state.wifi.ssid
            )
            expected_target = {
                "dns": profile.dns_query,
                "internet": profile.internet_target,
                "application": profile.https_url,
            }.get(domain.domain)
            if expected_target and item.target != expected_target:
                context_valid = False
            valid = (
                domain_available
                and item.quality == "current"
                and meta
                and meta.profile_version == version
                and context_valid
            )
            if not availability and outcome.value is not True:
                valid = False
            if not availability and (
                isinstance(item.value, bool)
                or not isinstance(item.value, (int, float))
                or not isfinite(item.value)
                or item.value < 0
                or (item.metric.endswith("_packet_loss_percent") and item.value > 100)
            ):
                valid = False
            if not valid or not item.observed_at:
                _unknown(
                    entry,
                    "Current evidence, applied profile or compatible Wi-Fi context is missing; "
                    "recovery is not confirmed.",
                )
                continue
            time = item.observed_at.astimezone(UTC)
            iso = time.isoformat()
            if entry.get("last_seen") and time <= timestamp(entry["last_seen"]):
                continue
            gap = bool(
                entry.get("last_seen")
                and (time - timestamp(entry["last_seen"])).total_seconds() > 30
            )
            if entry.get("context") != context:
                context_changed = bool(entry.get("context"))
                last_seen = entry.get("last_seen")
                entry.clear()
                entry.update(
                    rule_id=item.metric,
                    domain=domain.domain,
                    metric=item.metric,
                    label=item.label,
                    unit=item.unit,
                    target=item.target,
                    objective=objective,
                    status="unknown",
                    context=context,
                    last_seen=last_seen,
                )
                gap = gap or context_changed
            entry.update(last_seen=iso, observed_at=iso, value=item.value)
            if gap:
                entry.update(
                    bad_since=None,
                    good_since=None,
                    consecutive_samples=0,
                    last_bad=None,
                    evidence_gap=True,
                )
            ref_key = sha256(repr((item.metric, sorted(context.items()))).encode()).hexdigest()
            ref = (
                references.setdefault(
                    ref_key, {"samples": [], "summary": {"status": "forming", "samples": 0}}
                )
                if not availability and item.unit == "ms"
                else None
            )
            baseline = (
                deepcopy(ref["summary"]) if ref else {"status": "not_applicable", "samples": 0}
            )
            absolute_bad = not availability and objective is not None and item.value > objective
            relative_bad = baseline["status"] == "ready" and item.value > baseline["upper_limit"]
            bad = item.value is False if availability else absolute_bad or relative_bad
            # Recovery uses a separate lower boundary, preventing threshold chatter.
            if not availability and entry.get("confirmed") and not bad:
                if (objective is not None and item.value > objective * 0.8) or (
                    baseline["status"] == "ready"
                    and item.value
                    > baseline["median"] + (baseline["upper_limit"] - baseline["median"]) * 0.8
                ):
                    entry.update(
                        status="active",
                        good_since=None,
                        consecutive_samples=0,
                        reason="Still above the recovery boundary "
                        "(80% of the objective/relative range).",
                    )
                    continue
            entry["kind"] = (
                "availability"
                if availability
                else "objective"
                if absolute_bad
                else "relative"
                if relative_bad
                else entry.get("kind", "none")
            )
            entry["reason"] = (
                "Explicit disconnection or failed test observed."
                if availability and bad
                else "Configured performance objective exceeded."
                if absolute_bad
                else "Above the frozen reference for this client, target and Wi-Fi context."
                if relative_bad
                else "New successful evidence satisfies the recovery boundary."
                if entry.get("confirmed")
                else "The latest observation satisfies the configured rule."
            )
            _advance(
                entry, bad=bool(bad), immediate=availability, time=time, profile=profile, gap=gap
            )
            # Learn successful observations under the objective, outside candidates and alerts.
            # Once ready, freeze the reference instead of silently learning a degraded new normal.
            if ref and baseline["status"] == "forming" and not bad and entry["status"] == "normal":
                samples = ref["samples"]
                samples.append([iso, item.value])
                del samples[:-MAX_REFERENCE_SAMPLES]
                baseline["samples"] = len(samples)
                if (
                    len(samples) >= profile.baseline_min_samples
                    and (time - timestamp(samples[0][0])).total_seconds()
                    >= profile.baseline_min_seconds
                ):
                    baseline = _reference(samples, iso)
                    floor = (
                        100
                        if domain.domain == "application"
                        else 50
                        if domain.domain == "dns"
                        else 20
                        if domain.domain == "internet"
                        else 10
                    )
                    baseline["upper_limit"] = max(
                        baseline["p95"] + floor,
                        baseline["median"]
                        + max(6 * 1.4826 * baseline["mad"], baseline["median"] * 0.5, floor),
                    )
                    ref["samples"] = []
                ref["summary"] = baseline
            entry["baseline"] = baseline
            # Dict insertion order gives a deterministic bounded cache of context references.
            if len(references) > MAX_REFERENCES:
                references.pop(next(iter(references)))
    return result
