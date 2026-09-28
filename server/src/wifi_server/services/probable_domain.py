"""Conservative, deterministic probable-domain inference for a focused window."""

from wifi_server.recording_schemas import (
    DiagnosticEvidenceDomainSummary,
    DiagnosticProbableDomainAssessment,
    EvidenceDomain,
    ProbableDomainAssessmentStatus,
)

METHOD = "earliest-supported-domain-v1"
_DOMAIN_ORDER: tuple[EvidenceDomain, ...] = (
    "wifi_rf",
    "local_network",
    "dns",
    "internet",
    "application",
)


def assess_probable_domain(
    evidence_domains: list[DiagnosticEvidenceDomainSummary],
) -> DiagnosticProbableDomainAssessment:
    """Identify the earliest supported degraded domain without claiming root cause."""
    status_by_domain = {item.domain: item.status for item in evidence_domains}
    degraded_domains = [
        domain for domain in _DOMAIN_ORDER if status_by_domain.get(domain) == "degraded"
    ]
    unresolved_domains = [
        domain
        for domain in _DOMAIN_ORDER
        if status_by_domain.get(domain, "unavailable") == "unavailable"
    ]

    def assessment(
        status: ProbableDomainAssessmentStatus,
        rationale: str,
        domain: EvidenceDomain | None = None,
    ) -> DiagnosticProbableDomainAssessment:
        return DiagnosticProbableDomainAssessment(
            method=METHOD,
            status=status,
            domain=domain,
            degraded_domains=degraded_domains,
            unresolved_domains=unresolved_domains,
            rationale=rationale,
        )

    if not degraded_domains:
        return assessment(
            "not_observed",
            "No threshold-qualified deterioration was observed in the evaluated evidence domains.",
        )

    wifi_status = status_by_domain.get("wifi_rf", "unavailable")
    local_status = status_by_domain.get("local_network", "unavailable")
    dns_status = status_by_domain.get("dns", "unavailable")
    internet_status = status_by_domain.get("internet", "unavailable")
    application_status = status_by_domain.get("application", "unavailable")

    if wifi_status == "degraded":
        return assessment(
            "probable",
            (
                "Wi-Fi / RF is the earliest monitored domain with threshold-qualified "
                "deterioration in this interval. Downstream degradation may represent "
                "propagated impact, but this does not establish root cause."
            ),
            "wifi_rf",
        )

    if wifi_status == "unavailable":
        return assessment(
            "insufficient_evidence",
            (
                "Wi-Fi / RF evidence is unavailable, so an earlier client-link degradation "
                "cannot be excluded."
            ),
        )

    if local_status == "degraded":
        return assessment(
            "probable",
            (
                "Wi-Fi / RF shows no significant change while the local-network domain "
                "has threshold-qualified deterioration."
            ),
            "local_network",
        )

    if local_status == "unavailable":
        return assessment(
            "insufficient_evidence",
            (
                "Local-network evidence is unavailable, so a first-hop degradation cannot "
                "be excluded before the degraded downstream domains."
            ),
        )

    if internet_status == "degraded" and dns_status == "degraded":
        return assessment(
            "ambiguous",
            (
                "Internet and DNS are both degraded while Wi-Fi / RF and local-network "
                "evidence show no significant change. Their relative origin cannot be "
                "ordered with the current probes."
            ),
        )

    if internet_status == "degraded":
        return assessment(
            "probable",
            (
                "Wi-Fi / RF and local-network evidence show no significant change while "
                "Internet evidence has threshold-qualified deterioration."
            ),
            "internet",
        )

    if dns_status == "degraded":
        return assessment(
            "probable",
            (
                "Wi-Fi / RF and local-network evidence show no significant change while "
                "DNS evidence has threshold-qualified deterioration."
            ),
            "dns",
        )

    if application_status == "degraded":
        if internet_status == "unavailable" or dns_status == "unavailable":
            return assessment(
                "insufficient_evidence",
                (
                    "Application evidence is degraded, but Internet or DNS evidence is "
                    "unavailable, so an upstream service dependency cannot be excluded."
                ),
            )
        return assessment(
            "probable",
            (
                "Wi-Fi / RF, local-network, Internet and DNS evidence show no significant "
                "change while application evidence has threshold-qualified deterioration."
            ),
            "application",
        )

    return assessment(
        "insufficient_evidence",
        "The observed degraded domains do not satisfy a supported v1 inference pattern.",
    )
