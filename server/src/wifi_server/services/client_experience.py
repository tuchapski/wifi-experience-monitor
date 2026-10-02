"""Evaluate availability using each observation's clock, never the snapshot clock alone."""

from datetime import UTC, datetime
from math import isfinite

from fastapi import HTTPException
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, AgentCurrentState
from wifi_server.experience_schemas import (
    ClientExperienceResponse,
    ExperienceDomain,
    ExperienceMeasurement,
)
from wifi_server.schemas import AgentCurrentStateResponse
from wifi_server.services.agents import _current_state_response, is_agent_online

MAX_AGE = 30.0
FUTURE_TOLERANCE = 5.0
# Outcome first; the remaining measurements describe context and never imply success.
DOMAIN_METRICS = (
    (
        "wifi_rf",
        "Wi-Fi",
        "connected",
        (
            ("connected", "Association", None),
            ("rssi_dbm", "Signal", "dBm"),
            ("tx_retries_per_100_packets", "TX retries", "/100 packets"),
            ("tx_failed_percent", "TX failures", "%"),
        ),
    ),
    (
        "local_network",
        "Local network",
        "gateway_reachable",
        (
            ("gateway_reachable", "Reachability", None),
            ("gateway_latency_ms", "Latency", "ms"),
            ("gateway_packet_loss_percent", "Packet loss", "%"),
            ("gateway_jitter_ms", "Jitter", "ms"),
            ("gateway_latency_max_ms", "Maximum RTT", "ms"),
            ("gateway_packets_sent", "Packets sent", "packets"),
            ("gateway_packets_received", "Replies", "packets"),
        ),
    ),
    (
        "dns",
        "DNS",
        "dns_success",
        (
            ("dns_success", "Resolution", None),
            ("dns_latency_ms", "Latency", "ms"),
        ),
    ),
    (
        "internet",
        "Internet",
        "internet_reachable",
        (
            ("internet_reachable", "Reachability", None),
            ("internet_latency_ms", "Latency", "ms"),
            ("internet_packet_loss_percent", "Packet loss", "%"),
            ("internet_jitter_ms", "Jitter", "ms"),
            ("internet_latency_max_ms", "Maximum RTT", "ms"),
            ("internet_packets_sent", "Packets sent", "packets"),
            ("internet_packets_received", "Replies", "packets"),
        ),
    ),
    (
        "application",
        "Application",
        "https_success",
        (
            ("https_success", "HTTP outcome", None),
            ("https_total_ms", "Total time", "ms"),
            ("https_status_code", "HTTP status", None),
            ("https_ttfb_ms", "TTFB", "ms"),
            ("https_failure_elapsed_ms", "Failure elapsed", "ms"),
        ),
    ),
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def evaluate_client_experience(
    agent_id: str,
    state: AgentCurrentStateResponse | None,
    *,
    online: bool,
    now: datetime,
) -> ClientExperienceResponse:
    now = _utc(now)
    state_age = (now - _utc(state.observed_at)).total_seconds() if state else None
    snapshot_current = (
        online and state_age is not None and -FUTURE_TOLERANCE <= state_age <= MAX_AGE
    )

    def measurement(prefix: str, key: str, label: str, unit: str | None) -> ExperienceMeasurement:
        metric = f"{prefix}.{key}"
        values = getattr(state, prefix).model_dump() if state else {}
        value = values.get(key)
        metadata = state.measurement_metadata.get(metric) if state else None
        age = (now - metadata.observed_at).total_seconds() if metadata else None
        quality = "current"
        if value is None:
            quality = "unavailable"
        elif isinstance(value, float) and not isfinite(value):
            value, quality = None, "invalid"
        elif age is not None and age < -FUTURE_TOLERANCE:
            quality = "invalid"
        elif (
            metadata
            and state
            and (
                (
                    metadata.labels.get("interface")
                    and state.wifi.interface
                    and metadata.labels["interface"] != state.wifi.interface
                )
                or (
                    key.startswith("gateway_")
                    and metadata.labels.get("target")
                    and state.network.gateway
                    and metadata.labels["target"] != state.network.gateway
                )
            )
        ):
            quality = "invalid"
        elif not snapshot_current or (age is not None and age > MAX_AGE):
            quality = "stale"
        elif metadata is None:
            quality = "legacy"
        return ExperienceMeasurement(
            metric=metric,
            label=label,
            value=value,
            unit=unit,
            quality=quality,
            observed_at=metadata.observed_at if metadata else None,
            source=metadata.source if metadata else None,
            age_seconds=round(max(0, age), 3) if age is not None else None,
            sample_count=metadata.sample_count if metadata else None,
            interval_seconds=metadata.interval_seconds if metadata else None,
            target=metadata.labels.get("target") if metadata else None,
            profile_version=metadata.profile_version if metadata else None,
        )

    domains = []
    current_outcomes = 0
    for domain, label, _outcome_key, definitions in DOMAIN_METRICS:
        prefix = "wifi" if domain == "wifi_rf" else "network"
        measurements = [measurement(prefix, *definition) for definition in definitions]
        outcome = measurements[0]
        error_key = {
            "local_network": "gateway",
            "dns": "dns",
            "internet": "internet",
            "application": "https",
        }.get(domain)
        error = (
            measurement("network", f"{error_key}_collection_error", "Collection error", None)
            if error_key
            else None
        )
        if error and error.value:
            measurements.append(error)
        legacy_errors = []
        if state:
            error_fragments = {
                "wifi_rf": ("iw link failed", "iw info failed"),
                "local_network": (
                    "gateway ping collection failed",
                    "synthetic gateway probe failed",
                ),
                "dns": ("dns collection failed", "synthetic dns probe failed"),
                "internet": ("internet ping collection failed", "synthetic internet probe failed"),
                "application": ("https collection failed", "synthetic https probe failed"),
            }[domain]
            legacy_errors = [
                message
                for message in state.collector_errors
                if any(fragment in message.lower() for fragment in error_fragments)
            ]
        if state is not None and not snapshot_current:
            status, explanation = (
                "stale",
                "Agent is offline, or its state is stale or has an inconsistent clock.",
            )
        elif error and error.value and error.quality in {"current", "legacy"}:
            status, explanation = "collection_error", str(error.value)
        elif legacy_errors:
            status, explanation = "collection_error", "; ".join(legacy_errors)
        elif outcome.quality == "stale":
            status, explanation = "stale", "The latest outcome is older than 30 seconds."
        elif outcome.quality == "current" and type(outcome.value) is bool:
            current_outcomes += 1
            status = "observed_ok" if outcome.value else "failure"
            explanation = (
                "Association observed; service performance is evaluated separately."
                if domain == "wifi_rf" and outcome.value
                else (
                    "The configured test responded successfully; latency has no "
                    "performance objective in this view."
                    if outcome.value
                    else "The latest observation reports disconnection or a failed test."
                )
            )
            loss = next(
                (item for item in measurements if item.metric.endswith("_packet_loss_percent")),
                None,
            )
            if (
                outcome.value
                and loss
                and loss.quality == "current"
                and isinstance(loss.value, (float, int))
                and not isinstance(loss.value, bool)
                and loss.value > 0
            ):
                status, explanation = (
                    "degraded",
                    "The target responded, but some ICMP probes had no reply.",
                )
        elif outcome.quality in {"legacy", "invalid"} or outcome.value is not None:
            status, explanation = (
                "partial",
                "Outcome timing or validity is unavailable; these readings cannot "
                "certify current availability.",
            )
        else:
            status, explanation = "unavailable", "No valid test outcome is available."
        domains.append(
            ExperienceDomain(
                domain=domain,
                label=label,
                status=status,
                explanation=explanation,
                target=outcome.target or (error.target if error else None),
                measurements=measurements,
            )
        )

    statuses = {item.status for item in domains}
    if "failure" in statuses:
        overall = "failure"
    elif "degraded" in statuses:
        overall = "degraded"
    elif statuses == {"observed_ok"}:
        overall = "observed_ok"
    elif statuses == {"stale"}:
        overall = "stale"
    elif statuses == {"unavailable"}:
        overall = "unavailable"
    else:
        overall = "partial"
    return ClientExperienceResponse(
        agent_id=agent_id,
        evaluated_at=now,
        agent_online=online,
        state_observed_at=state.observed_at if state else None,
        state_received_at=state.updated_at if state else None,
        status=overall,
        current_outcomes=current_outcomes,
        outcome_coverage_percent=round(current_outcomes / len(domains) * 100, 1),
        domains=domains,
        collector_errors=state.collector_errors if state else [],
        limitations=[
            "Availability describes this client and its configured targets; "
            "it is not a WLAN-wide assessment.",
            "Latency objectives, historical baselines and sustained anomaly detection "
            "are not evaluated here.",
            "Legacy Agents without observation timestamps remain partial until "
            "they publish measurement metadata.",
        ],
    )


def get_client_experience(
    session: Session, settings: ServerSettings, agent_id: str
) -> ClientExperienceResponse:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    current = session.get(AgentCurrentState, agent_id)
    now = datetime.now(UTC)
    return evaluate_client_experience(
        agent_id,
        _current_state_response(current) if current else None,
        online=is_agent_online(_utc(agent.last_seen_at), now, settings.agent_offline_after_seconds),
        now=now,
    )
