from dataclasses import dataclass
from datetime import UTC, datetime

from wem.models.metrics import (
    DiagnosticFinding,
    DiagnosticResult,
    Incident,
    IncidentEvaluation,
    IncidentEvent,
)


@dataclass(slots=True)
class _IncidentTracker:
    code: str
    domain: str
    severity: str
    message: str

    first_seen_at: str

    consecutive_occurrences: int = 0
    consecutive_recoveries: int = 0

    active: bool = False

    opened_at: str | None = None


class IncidentEngine:
    def __init__(
        self,
        warning_open_samples: int = 3,
        critical_open_samples: int = 2,
        resolve_samples: int = 3,
    ):
        if warning_open_samples < 1:
            raise ValueError("warning_open_samples must be >= 1")

        if critical_open_samples < 1:
            raise ValueError("critical_open_samples must be >= 1")

        if resolve_samples < 1:
            raise ValueError("resolve_samples must be >= 1")

        self.warning_open_samples = warning_open_samples

        self.critical_open_samples = critical_open_samples

        self.resolve_samples = resolve_samples

        self._trackers: dict[
            str,
            _IncidentTracker,
        ] = {}

    def restore_active_incident(
        self,
        code: str,
        domain: str,
        severity: str,
        message: str,
        first_seen_at: str,
        opened_at: str,
    ) -> None:
        self._trackers[code] = _IncidentTracker(
            code=code,
            domain=domain,
            severity=severity,
            message=message,
            first_seen_at=first_seen_at,
            consecutive_occurrences=(self._required_open_samples(severity)),
            consecutive_recoveries=0,
            active=True,
            opened_at=opened_at,
        )

    def evaluate(
        self,
        diagnostic: DiagnosticResult,
        timestamp: str | None = None,
        fresh_domains: set[str] | None = None,
        fresh_codes: set[str] | None = None,
    ) -> IncidentEvaluation:
        now = timestamp or datetime.now(UTC).isoformat()

        relevant_findings = {
            finding.code: finding
            for finding in diagnostic.findings
            if finding.severity
            in {
                "warning",
                "critical",
            }
        }

        events: list[IncidentEvent] = []

        self._process_present_findings(
            findings=relevant_findings,
            timestamp=now,
            events=events,
            fresh_domains=fresh_domains,
            fresh_codes=fresh_codes,
        )

        if diagnostic.complete:
            self._process_missing_findings(
                present_codes=set(relevant_findings),
                timestamp=now,
                events=events,
                fresh_domains=fresh_domains,
                fresh_codes=fresh_codes,
            )
        else:
            for code, tracker in self._trackers.items():
                if code not in relevant_findings and (
                    fresh_domains is None or tracker.domain in fresh_domains
                ):
                    tracker.consecutive_recoveries = 0
                    tracker.consecutive_occurrences = 0

        active_incidents = [
            self._tracker_to_incident(tracker)
            for tracker in self._trackers.values()
            if tracker.active
        ]

        active_incidents.sort(
            key=lambda incident: (
                self._severity_priority(incident.severity),
                incident.opened_at or "",
            ),
            reverse=True,
        )

        return IncidentEvaluation(
            active_incidents=(active_incidents),
            events=events,
        )

    def _process_present_findings(
        self,
        findings: dict[
            str,
            DiagnosticFinding,
        ],
        timestamp: str,
        events: list[IncidentEvent],
        fresh_domains: set[str] | None,
        fresh_codes: set[str] | None,
    ) -> None:
        for (
            code,
            finding,
        ) in findings.items():
            if fresh_domains is not None and finding.domain not in fresh_domains:
                continue
            if fresh_codes is not None and code not in fresh_codes:
                continue
            tracker = self._trackers.get(code)

            if tracker is None:
                tracker = _IncidentTracker(
                    code=finding.code,
                    domain=(finding.domain),
                    severity=(finding.severity),
                    message=(finding.message),
                    first_seen_at=(timestamp),
                )

                self._trackers[code] = tracker

            tracker.domain = finding.domain

            tracker.severity = finding.severity

            tracker.message = finding.message

            tracker.consecutive_occurrences += 1

            tracker.consecutive_recoveries = 0

            if tracker.active:
                continue

            required_samples = self._required_open_samples(finding.severity)

            if tracker.consecutive_occurrences < required_samples:
                continue

            tracker.active = True

            tracker.opened_at = timestamp

            events.append(
                IncidentEvent(
                    action="opened",
                    code=tracker.code,
                    domain=tracker.domain,
                    severity=tracker.severity,
                    message=tracker.message,
                    first_seen_at=(tracker.first_seen_at),
                    opened_at=(tracker.opened_at),
                    resolved_at=None,
                )
            )

    def _process_missing_findings(
        self,
        present_codes: set[str],
        timestamp: str,
        events: list[IncidentEvent],
        fresh_domains: set[str] | None,
        fresh_codes: set[str] | None,
    ) -> None:
        for (
            code,
            tracker,
        ) in list(self._trackers.items()):
            if code in present_codes:
                continue

            if fresh_domains is not None and tracker.domain not in fresh_domains:
                continue

            if fresh_codes is not None and code not in fresh_codes:
                continue

            if not tracker.active:
                del self._trackers[code]

                continue

            tracker.consecutive_occurrences = 0

            tracker.consecutive_recoveries += 1

            if tracker.consecutive_recoveries < self.resolve_samples:
                continue

            events.append(
                IncidentEvent(
                    action="resolved",
                    code=tracker.code,
                    domain=tracker.domain,
                    severity=tracker.severity,
                    message=tracker.message,
                    first_seen_at=(tracker.first_seen_at),
                    opened_at=(tracker.opened_at),
                    resolved_at=timestamp,
                )
            )

            del self._trackers[code]

    def _required_open_samples(
        self,
        severity: str,
    ) -> int:
        if severity == "critical":
            return self.critical_open_samples

        return self.warning_open_samples

    @staticmethod
    def _severity_priority(
        severity: str,
    ) -> int:
        priorities = {
            "critical": 3,
            "warning": 2,
            "info": 1,
        }

        return priorities.get(
            severity,
            0,
        )

    @staticmethod
    def _tracker_to_incident(
        tracker: _IncidentTracker,
    ) -> Incident:
        return Incident(
            code=tracker.code,
            domain=tracker.domain,
            severity=tracker.severity,
            message=tracker.message,
            first_seen_at=(tracker.first_seen_at),
            opened_at=(tracker.opened_at),
            consecutive_occurrences=(tracker.consecutive_occurrences),
        )
