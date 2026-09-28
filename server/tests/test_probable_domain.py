"""Probable-domain inference remains deterministic and non-causal."""

import pytest
from wifi_server.recording_schemas import DiagnosticEvidenceDomainSummary
from wifi_server.services.probable_domain import assess_probable_domain

DOMAINS = ("wifi_rf", "local_network", "dns", "internet", "application")


def _summaries(**statuses: str) -> list[DiagnosticEvidenceDomainSummary]:
    return [
        DiagnosticEvidenceDomainSummary(
            domain=domain,
            status=statuses.get(domain, "unavailable"),
            evaluated_metrics=[],
            finding_metrics=[],
        )
        for domain in DOMAINS
    ]


@pytest.mark.parametrize(
    ("statuses", "expected_domain"),
    [
        (
            {
                "wifi_rf": "degraded",
                "local_network": "degraded",
                "dns": "no_significant_change",
                "internet": "degraded",
                "application": "degraded",
            },
            "wifi_rf",
        ),
        (
            {
                "wifi_rf": "no_significant_change",
                "local_network": "degraded",
                "dns": "no_significant_change",
                "internet": "degraded",
                "application": "degraded",
            },
            "local_network",
        ),
        (
            {
                "wifi_rf": "no_significant_change",
                "local_network": "no_significant_change",
                "dns": "no_significant_change",
                "internet": "degraded",
                "application": "degraded",
            },
            "internet",
        ),
        (
            {
                "wifi_rf": "no_significant_change",
                "local_network": "no_significant_change",
                "dns": "degraded",
                "internet": "no_significant_change",
                "application": "degraded",
            },
            "dns",
        ),
        (
            {
                "wifi_rf": "no_significant_change",
                "local_network": "no_significant_change",
                "dns": "no_significant_change",
                "internet": "no_significant_change",
                "application": "degraded",
            },
            "application",
        ),
    ],
)
def test_probable_domain_selects_earliest_supported_domain(
    statuses: dict[str, str],
    expected_domain: str,
) -> None:
    result = assess_probable_domain(_summaries(**statuses))

    assert result.method == "earliest-supported-domain-v1"
    assert result.status == "probable"
    assert result.domain == expected_domain


def test_probable_domain_marks_parallel_dns_and_internet_degradation_ambiguous() -> None:
    result = assess_probable_domain(
        _summaries(
            wifi_rf="no_significant_change",
            local_network="no_significant_change",
            dns="degraded",
            internet="degraded",
            application="degraded",
        )
    )

    assert result.status == "ambiguous"
    assert result.domain is None
    assert result.degraded_domains == ["dns", "internet", "application"]


def test_probable_domain_requires_missing_earlier_evidence() -> None:
    result = assess_probable_domain(
        _summaries(
            wifi_rf="unavailable",
            local_network="degraded",
            dns="no_significant_change",
            internet="degraded",
            application="degraded",
        )
    )

    assert result.status == "insufficient_evidence"
    assert result.domain is None
    assert "wifi_rf" in result.unresolved_domains


def test_probable_domain_reports_no_observed_degradation_without_claiming_health() -> None:
    result = assess_probable_domain(
        _summaries(
            wifi_rf="no_significant_change",
            local_network="no_significant_change",
            dns="no_significant_change",
            internet="no_significant_change",
            application="unavailable",
        )
    )

    assert result.status == "not_observed"
    assert result.domain is None
    assert result.unresolved_domains == ["application"]
