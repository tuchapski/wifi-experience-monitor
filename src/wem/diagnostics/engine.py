from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    DiagnosticFinding,
    DiagnosticResult,
    WifiDeltaMetrics,
    WifiMetrics,
)
from wem.profiles.defaults import default_profile_config
from wem.profiles.models import TestProfileConfig


class DiagnosticEngine:
    def __init__(self, profile: TestProfileConfig | None = None) -> None:
        self.profile = (profile or default_profile_config()).model_copy(deep=True)

    def analyze(
        self,
        wifi: WifiMetrics,
        wifi_delta: WifiDeltaMetrics | None,
        connectivity: ConnectivityMetrics,
        calibration: CalibrationResult | None = None,
        collector_errors: list[str] | None = None,
    ) -> DiagnosticResult:
        findings: list[DiagnosticFinding] = []
        complete = wifi.associated is not None and wifi.signal_dbm is not None
        result_fields = {
            "gateway": connectivity.gateway_reachable,
            "dns": connectivity.dns_success,
            "internet": connectivity.internet_reachable,
            "https": connectivity.https_success,
        }
        for name, value in result_fields.items():
            test = getattr(self.profile.tests, name)
            if test.enabled:
                outcome = connectivity.tests.get(name)
                complete = complete and value is not None
                if outcome is not None:
                    complete = complete and outcome.status in {"passed", "failed"}
        complete = complete and not collector_errors
        if calibration is not None:
            complete = complete and calibration.calibrated
            for finding in calibration.findings:
                findings.append(
                    DiagnosticFinding(
                        severity=finding.severity,
                        domain="sensor",
                        code=finding.code,
                        message=finding.message,
                    )
                )
        if collector_errors:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="sensor",
                    code="COLLECTION_ERROR",
                    message="Some measurements could not be collected. Inspect Sensor Errors.",
                )
            )

        self._check_wifi(
            wifi,
            wifi_delta,
            findings,
        )

        self._check_gateway(
            connectivity,
            findings,
        )

        self._check_dns(
            connectivity,
            findings,
        )

        self._check_internet(
            connectivity,
            findings,
        )

        self._check_application(
            connectivity,
            findings,
        )

        overall_status = self._overall_status(findings)

        if not complete and overall_status in {"healthy", "info"}:
            overall_status = "unknown"
        probable_domain = self._probable_domain(findings)

        return DiagnosticResult(
            overall_status=overall_status,
            complete=bool(complete),
            probable_domain=probable_domain,
            findings=findings,
        )

    def _check_wifi(
        self,
        wifi: WifiMetrics,
        wifi_delta: WifiDeltaMetrics | None,
        findings: list[DiagnosticFinding],
    ) -> None:
        if wifi.associated is False:
            findings.append(
                DiagnosticFinding(
                    severity="critical",
                    domain="wifi",
                    code="WIFI_NOT_ASSOCIATED",
                    message=("Wi-Fi interface is not associated with an access point."),
                )
            )
            return

        thresholds = self.profile.thresholds.wifi
        if wifi.signal_dbm is not None:
            if wifi.signal_dbm < thresholds.rssi_critical_dbm:
                findings.append(
                    DiagnosticFinding(
                        severity="critical",
                        domain="wifi",
                        code="WIFI_VERY_LOW_SIGNAL",
                        message=(f"Wi-Fi signal is below {thresholds.rssi_critical_dbm:g} dBm."),
                    )
                )

            elif wifi.signal_dbm < thresholds.rssi_warning_dbm:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        domain="wifi",
                        code="WIFI_LOW_SIGNAL",
                        message=(f"Wi-Fi signal is below {thresholds.rssi_warning_dbm:g} dBm."),
                    )
                )

        if wifi.beacon_loss is not None:
            if wifi.beacon_loss > 0:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        domain="wifi",
                        code="WIFI_BEACON_LOSS",
                        message=("Beacon loss was detected on the current association."),
                    )
                )

        if wifi_delta is None:
            return

        retry_rate = wifi_delta.tx_retries_per_100_packets

        if retry_rate is not None:
            if retry_rate >= thresholds.retry_critical_percent:
                findings.append(
                    DiagnosticFinding(
                        severity="critical",
                        domain="wifi",
                        code="WIFI_HIGH_RETRIES",
                        message=("Wi-Fi retransmission activity is very high."),
                    )
                )

            elif retry_rate >= thresholds.retry_warning_percent:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        domain="wifi",
                        code="WIFI_ELEVATED_RETRIES",
                        message=("Wi-Fi retransmission activity is elevated."),
                    )
                )

        if (
            wifi_delta.tx_failed_percent is not None
            and wifi_delta.tx_failed_percent >= thresholds.tx_failure_critical_percent
        ):
            findings.append(
                DiagnosticFinding(
                    severity="critical",
                    domain="wifi",
                    code="WIFI_TX_FAILURES",
                    message=("A high percentage of Wi-Fi transmissions are failing."),
                )
            )

        if wifi_delta.association_changed:
            findings.append(
                DiagnosticFinding(
                    severity="info",
                    domain="wifi",
                    code="WIFI_ROAM_DETECTED",
                    message=("The client changed access point during the interval."),
                )
            )

    def _check_gateway(
        self,
        connectivity: ConnectivityMetrics,
        findings: list[DiagnosticFinding],
    ) -> None:
        if connectivity.gateway_reachable is False:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="gateway",
                    code="GATEWAY_ICMP_FAILED",
                    message=(
                        "The gateway did not answer ICMP; filtering or rate limiting is possible."
                    ),
                )
            )
            return

        thresholds = self.profile.thresholds.gateway
        loss = connectivity.gateway_packet_loss_percent

        if loss is not None:
            if loss >= thresholds.packet_loss_critical_percent:
                findings.append(
                    DiagnosticFinding(
                        severity="critical",
                        domain="gateway",
                        code="GATEWAY_HIGH_PACKET_LOSS",
                        message=("High packet loss was detected to the gateway."),
                    )
                )

            elif loss >= thresholds.packet_loss_warning_percent:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        domain="gateway",
                        code="GATEWAY_PACKET_LOSS",
                        message=("Packet loss was detected to the gateway."),
                    )
                )

        latency = connectivity.gateway_latency_avg_ms

        if latency is not None and latency >= thresholds.latency_warning_ms:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="gateway",
                    code="GATEWAY_HIGH_LATENCY",
                    message=("Gateway latency is higher than expected for a local network."),
                )
            )

    def _check_dns(
        self,
        connectivity: ConnectivityMetrics,
        findings: list[DiagnosticFinding],
    ) -> None:
        if connectivity.dns_success is False:
            findings.append(
                DiagnosticFinding(
                    severity="critical",
                    domain="dns",
                    code="DNS_FAILURE",
                    message=("DNS resolution failed."),
                )
            )
            return

        latency = connectivity.dns_latency_ms

        if latency is not None and latency >= self.profile.thresholds.dns.latency_warning_ms:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="dns",
                    code="DNS_HIGH_LATENCY",
                    message=("DNS resolution latency is high."),
                )
            )

    def _check_internet(
        self,
        connectivity: ConnectivityMetrics,
        findings: list[DiagnosticFinding],
    ) -> None:
        if connectivity.internet_reachable is False:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="internet",
                    code="INTERNET_ICMP_FAILED",
                    message=(
                        "External ICMP test failed. "
                        + (
                            "DNS or HTTPS succeeded via the host route; "
                            "general Internet failure is not established."
                            if connectivity.dns_success is True
                            or connectivity.https_success is True
                            else "No independent success confirms connectivity; "
                            "investigate the configured targets."
                        )
                    ),
                )
            )
            return

        thresholds = self.profile.thresholds.internet
        loss = connectivity.internet_packet_loss_percent

        if loss is not None:
            if loss >= thresholds.packet_loss_critical_percent:
                findings.append(
                    DiagnosticFinding(
                        severity="critical",
                        domain="internet",
                        code="INTERNET_HIGH_PACKET_LOSS",
                        message=("High packet loss was detected toward the Internet."),
                    )
                )

            elif loss >= thresholds.packet_loss_warning_percent:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        domain="internet",
                        code="INTERNET_PACKET_LOSS",
                        message=("Packet loss was detected toward the Internet."),
                    )
                )

        latency = connectivity.internet_latency_avg_ms

        if latency is not None and latency >= thresholds.latency_warning_ms:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="internet",
                    code="INTERNET_HIGH_LATENCY",
                    message=("Internet latency is high."),
                )
            )

    def _check_application(
        self,
        connectivity: ConnectivityMetrics,
        findings: list[DiagnosticFinding],
    ) -> None:
        if connectivity.https_success is False:
            findings.append(
                DiagnosticFinding(
                    severity="critical",
                    domain="application",
                    code="HTTPS_FAILURE",
                    message=("The HTTPS synthetic test failed."),
                )
            )
            return

        latency = connectivity.https_total_time_ms

        if latency is not None and latency >= self.profile.thresholds.https.response_warning_ms:
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    domain="application",
                    code="HTTPS_HIGH_RESPONSE_TIME",
                    message=("HTTPS response time is high."),
                )
            )

    @staticmethod
    def _overall_status(
        findings: list[DiagnosticFinding],
    ) -> str:
        if any(finding.severity == "critical" for finding in findings):
            return "critical"

        if any(finding.severity == "warning" for finding in findings):
            return "warning"

        if findings:
            return "info"

        return "healthy"

    @staticmethod
    def _probable_domain(
        findings: list[DiagnosticFinding],
    ) -> str | None:
        severity_priority = {
            "critical": 3,
            "warning": 2,
            "info": 1,
        }

        relevant = [finding for finding in findings if finding.severity in severity_priority]

        if not relevant:
            return None

        relevant.sort(
            key=lambda finding: severity_priority[finding.severity],
            reverse=True,
        )

        return relevant[0].domain
