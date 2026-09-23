from __future__ import annotations

from collections import defaultdict

from wem.models.metrics import (
    CorrelationAssessment,
    CorrelationEvidence,
    CorrelationHypothesis,
    DiagnosticFinding,
    SensorSnapshot,
)

_DOMAIN_LABELS = {
    "wifi": "Wi-Fi / radio access",
    "local_network": "Local network / gateway path",
    "dns": "DNS",
    "internet": "Internet / upstream path",
    "application": "Application / HTTPS target",
}

_EXACT_CODE_DOMAINS = {
    "SERVICE_SLO_GATEWAY": "local_network",
    "SERVICE_SLO_INTERNET": "internet",
    "SERVICE_SLO_DNS": "dns",
    "SERVICE_SLO_HTTPS": "application",
    "CONNECTION_CYCLE_ASSOCIATION_P95_SLO": "wifi",
    "CONNECTION_CYCLE_AUTHENTICATION_P95_SLO": "wifi",
    "CONNECTION_CYCLE_IPV4_P95_SLO": "local_network",
    "CONNECTION_CYCLE_GATEWAY_P95_SLO": "local_network",
    "CONNECTION_CYCLE_DNS_P95_SLO": "dns",
    "BASELINE_RSSI_DEVIATION": "wifi",
    "BASELINE_TX_RETRIES_DEVIATION": "wifi",
    "BASELINE_GATEWAY_LATENCY_DEVIATION": "local_network",
    "BASELINE_INTERNET_LATENCY_DEVIATION": "internet",
    "BASELINE_DNS_LATENCY_DEVIATION": "dns",
    "BASELINE_HTTPS_RESPONSE_DEVIATION": "application",
}

_DOMAIN_FROM_FINDING = {
    "wifi": "wifi",
    "gateway": "local_network",
    "dns": "dns",
    "internet": "internet",
    "application": "application",
}

_SUPPORT_RANK = {"weak": 1, "moderate": 2, "strong": 3}


class CorrelationEngine:
    """Build deterministic, explainable domain hypotheses from existing evidence."""

    policy_version = "correlation-v1"

    def evaluate(self, snapshot: SensorSnapshot) -> CorrelationAssessment:
        diagnostic = snapshot.diagnostic
        limitations = [
            "Correlation identifies the domain best supported by observed evidence; "
            "it does not prove a physical root cause."
        ]
        if diagnostic is None:
            return CorrelationAssessment(
                policy_version=self.policy_version,
                status="insufficient_data",
                primary_domain=None,
                limitations=limitations,
                reason="No diagnostic result is available to correlate.",
            )

        if not diagnostic.complete:
            limitations.append(
                "The base diagnostic is incomplete, so missing evidence is not treated as healthy."
            )
        if snapshot.collector_errors:
            limitations.append(
                "One or more collector errors are present and can reduce correlation coverage."
            )

        by_domain: dict[str, list[CorrelationEvidence]] = defaultdict(list)
        for finding in diagnostic.findings:
            if finding.severity not in {"warning", "critical"}:
                continue
            domain = self._domain_for_finding(finding)
            if domain is None:
                continue
            by_domain[domain].append(
                CorrelationEvidence(
                    code=finding.code,
                    source=self._source_for_code(finding.code),
                    severity=finding.severity,
                    message=finding.message,
                )
            )

        for domain in list(by_domain):
            by_domain[domain].extend(
                self._isolation_evidence(snapshot, domain, diagnostic.findings)
            )

        hypotheses = [
            self._hypothesis(domain, evidence)
            for domain, evidence in by_domain.items()
            if any(item.source != "isolation" for item in evidence)
        ]
        hypotheses.sort(key=lambda item: (-_SUPPORT_RANK[item.support], item.domain))

        if not hypotheses:
            status = (
                "insufficient_data"
                if not diagnostic.complete or snapshot.collector_errors
                else "no_degradation"
            )
            reason = (
                "No degradations can be localized because diagnostic coverage is incomplete."
                if status == "insufficient_data"
                else "No warning or critical evidence maps to a correlated degradation domain."
            )
            return CorrelationAssessment(
                policy_version=self.policy_version,
                status=status,
                primary_domain=None,
                hypotheses=[],
                limitations=limitations,
                reason=reason,
            )

        best_rank = _SUPPORT_RANK[hypotheses[0].support]
        leaders = [item for item in hypotheses if _SUPPORT_RANK[item.support] == best_rank]
        if len(leaders) == 1:
            primary_domain = leaders[0].domain
            status = "correlated"
            reason = (
                f"{leaders[0].label} has the highest deterministic evidence support "
                f"({leaders[0].support})."
            )
        else:
            primary_domain = None
            status = "ambiguous"
            labels = ", ".join(item.label for item in leaders)
            reason = (
                f"Multiple domains share the highest evidence support ({leaders[0].support}): "
                f"{labels}. No primary domain is selected."
            )

        if any(item.domain in {"dns", "application"} for item in hypotheses):
            limitations.append(
                "DNS and HTTPS synthetic tests follow the host route; their success or failure "
                "does not prove binding to the selected Wi-Fi interface."
            )

        return CorrelationAssessment(
            policy_version=self.policy_version,
            status=status,
            primary_domain=primary_domain,
            hypotheses=hypotheses,
            limitations=limitations,
            reason=reason,
        )

    @staticmethod
    def _domain_for_finding(finding: DiagnosticFinding) -> str | None:
        exact = _EXACT_CODE_DOMAINS.get(finding.code)
        if exact is not None:
            return exact
        if finding.code == "CONNECTION_CYCLE_P95_SLO":
            return None
        return _DOMAIN_FROM_FINDING.get(finding.domain)

    @staticmethod
    def _source_for_code(code: str) -> str:
        if code.startswith("SERVICE_SLO_"):
            return "rolling_service_slo"
        if code.startswith("BASELINE_"):
            return "adaptive_baseline"
        if code.startswith("CONNECTION_CYCLE_"):
            return "connection_cycle_slo"
        return "current_diagnostic"

    def _hypothesis(
        self,
        domain: str,
        evidence: list[CorrelationEvidence],
    ) -> CorrelationHypothesis:
        degradation = [item for item in evidence if item.source != "isolation"]
        isolation = [item for item in evidence if item.source == "isolation"]
        sources = {item.source for item in degradation}
        current = [item for item in degradation if item.source == "current_diagnostic"]
        critical_current = any(item.severity == "critical" for item in current)
        any_critical = any(item.severity == "critical" for item in degradation)

        if len(sources) >= 2 or (critical_current and isolation):
            support = "strong"
        elif any_critical or len(degradation) >= 2 or (current and isolation):
            support = "moderate"
        else:
            support = "weak"

        hypothesis_limitations: list[str] = []
        if not current:
            hypothesis_limitations.append(
                "This hypothesis is supported by historical/rolling evidence without an active "
                "single-sample diagnostic finding."
            )

        return CorrelationHypothesis(
            domain=domain,
            label=_DOMAIN_LABELS[domain],
            support=support,
            evidence=evidence,
            limitations=hypothesis_limitations,
        )

    @staticmethod
    def _isolation_evidence(
        snapshot: SensorSnapshot,
        domain: str,
        findings: list[DiagnosticFinding],
    ) -> list[CorrelationEvidence]:
        connectivity = snapshot.connectivity
        result: list[CorrelationEvidence] = []

        def add(code: str, message: str) -> None:
            result.append(
                CorrelationEvidence(
                    code=code,
                    source="isolation",
                    severity="info",
                    message=message,
                )
            )

        if domain == "local_network":
            wifi_degraded = any(
                item.domain == "wifi" and item.severity in {"warning", "critical"}
                for item in findings
            )
            if snapshot.wifi.associated is True and not wifi_degraded:
                add(
                    "ISOLATION_WIFI_ASSOCIATED",
                    "Wi-Fi is associated and no active Wi-Fi warning/critical finding is present.",
                )
        elif domain == "dns":
            if connectivity.gateway_reachable is True:
                add(
                    "ISOLATION_GATEWAY_REACHABLE",
                    "The local gateway is reachable in the current sample.",
                )
            if connectivity.internet_reachable is True:
                add(
                    "ISOLATION_INTERNET_REACHABLE",
                    "The external ICMP target is reachable in the current sample.",
                )
        elif domain == "internet":
            if connectivity.gateway_reachable is True:
                add(
                    "ISOLATION_GATEWAY_REACHABLE",
                    "The local gateway is reachable while Internet-path evidence is degraded.",
                )
        elif domain == "application":
            if connectivity.dns_success is True:
                add(
                    "ISOLATION_DNS_SUCCESS",
                    "DNS resolution succeeds in the current sample.",
                )
            if connectivity.internet_reachable is True:
                add(
                    "ISOLATION_INTERNET_REACHABLE",
                    "The external ICMP target is reachable in the current sample.",
                )

        return result
