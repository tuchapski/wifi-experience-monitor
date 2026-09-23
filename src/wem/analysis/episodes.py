from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}


@dataclass(frozen=True, slots=True)
class EpisodeIncident:
    id: int
    code: str
    domain: str
    severity: str
    message: str
    started_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class CorrelationObservation:
    observed_at: datetime
    status: str
    primary_domain: str | None


class ExperienceEpisodeEngine:
    """Group temporally related incidents into explainable experience episodes."""

    def __init__(self, merge_gap_seconds: int = 120) -> None:
        if merge_gap_seconds < 0:
            raise ValueError("merge_gap_seconds must be >= 0")
        self.merge_gap_seconds = merge_gap_seconds

    def build(
        self,
        incidents: list[EpisodeIncident],
        correlations: list[CorrelationObservation] | None = None,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        current_time = self._utc(now or datetime.now(UTC))
        if not incidents:
            return {"merge_gap_seconds": self.merge_gap_seconds, "episodes": []}

        ordered = sorted(incidents, key=lambda item: self._utc(item.started_at))
        clusters: list[list[EpisodeIncident]] = []
        current = [ordered[0]]
        current_end = self._effective_end(ordered[0], current_time)
        gap = timedelta(seconds=self.merge_gap_seconds)

        for incident in ordered[1:]:
            started_at = self._utc(incident.started_at)
            if started_at <= current_end + gap:
                current.append(incident)
                current_end = max(current_end, self._effective_end(incident, current_time))
                continue
            clusters.append(current)
            current = [incident]
            current_end = self._effective_end(incident, current_time)
        clusters.append(current)

        observations = correlations or []
        episodes = [self._episode(cluster, observations, current_time) for cluster in clusters]
        episodes.sort(key=lambda item: str(item["started_at"]), reverse=True)
        if limit is not None:
            episodes = episodes[:limit]
        return {"merge_gap_seconds": self.merge_gap_seconds, "episodes": episodes}

    def _episode(
        self,
        incidents: list[EpisodeIncident],
        correlations: list[CorrelationObservation],
        now: datetime,
    ) -> dict[str, object]:
        started_at = min(self._utc(item.started_at) for item in incidents)
        active = any(item.resolved_at is None for item in incidents)
        ended_at = None
        if not active:
            resolved = [self._utc(item.resolved_at) for item in incidents if item.resolved_at]
            ended_at = max(resolved)
        effective_end = now if ended_at is None else ended_at
        correlation = self._correlation(correlations, started_at, effective_end)

        severity = max(
            (item.severity for item in incidents),
            key=lambda value: _SEVERITY_RANK.get(value, 0),
        )
        ordered_incidents = sorted(incidents, key=lambda item: self._utc(item.started_at))
        return {
            "episode_id": f"episode-{ordered_incidents[0].id}",
            "status": "active" if active else "ended",
            "severity": severity,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat() if ended_at is not None else None,
            "duration_seconds": max(0.0, (effective_end - started_at).total_seconds()),
            "incident_count": len(incidents),
            "incident_ids": [item.id for item in ordered_incidents],
            "codes": self._unique(item.code for item in ordered_incidents),
            "domains": self._unique(item.domain for item in ordered_incidents),
            **correlation,
        }

    @staticmethod
    def _correlation(
        observations: list[CorrelationObservation],
        start: datetime,
        end: datetime,
    ) -> dict[str, object]:
        domains = [
            item.primary_domain
            for item in observations
            if start <= ExperienceEpisodeEngine._utc(item.observed_at) <= end
            and item.status == "correlated"
            and item.primary_domain is not None
        ]
        counts = Counter(domains)
        domain_counts = dict(sorted(counts.items()))
        if not counts:
            return {
                "correlation_status": "unavailable",
                "primary_domain": None,
                "correlation_sample_count": 0,
                "correlation_domain_counts": {},
                "correlation_reason": (
                    "No correlated warning/critical snapshot is available inside this episode."
                ),
            }
        if len(counts) == 1:
            domain = next(iter(counts))
            count = counts[domain]
            return {
                "correlation_status": "correlated",
                "primary_domain": domain,
                "correlation_sample_count": count,
                "correlation_domain_counts": domain_counts,
                "correlation_reason": (
                    f"All {count} correlated snapshot(s) in the episode point to {domain}."
                ),
            }
        return {
            "correlation_status": "mixed",
            "primary_domain": None,
            "correlation_sample_count": sum(counts.values()),
            "correlation_domain_counts": domain_counts,
            "correlation_reason": (
                "Correlated snapshots point to more than one domain; the episode is not "
                "assigned a single primary domain."
            ),
        }

    @staticmethod
    def _effective_end(incident: EpisodeIncident, now: datetime) -> datetime:
        if incident.resolved_at is None:
            return now
        return ExperienceEpisodeEngine._utc(incident.resolved_at)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value not in result:
                result.append(value)
        return result
