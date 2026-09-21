from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    DiagnosticResult,
    EnvironmentChange,
    Recommendation,
    WifiDeltaMetrics,
    WifiMetrics,
)


class RecommendationEngine:
    """Turn observed findings into bounded, explainable next actions."""

    _GUIDANCE = {
        "WIFI_VERY_LOW_SIGNAL": (
            "critical",
            "Investigate Wi-Fi coverage",
            (
                "Measure the location with a site survey, check AP placement "
                "and verify that the client is not at a cell edge."
            ),
            "Very low RSSI can cause low rates, retries and roaming instability.",
        ),
        "WIFI_LOW_SIGNAL": (
            "warning",
            "Improve Wi-Fi coverage",
            (
                "Check AP placement and client location; compare nearby AP "
                "signal before changing RF settings."
            ),
            "The client signal is below the recommended operating range.",
        ),
        "WIFI_HIGH_RETRIES": (
            "critical",
            "Investigate RF quality",
            (
                "Check channel utilization, co-channel interference, channel "
                "width and client/AP compatibility."
            ),
            "A high retry ratio means the radio is retransmitting frequently.",
        ),
        "WIFI_ELEVATED_RETRIES": (
            "warning",
            "Review RF conditions",
            (
                "Compare retries with RSSI, channel utilization and nearby APs "
                "before changing channels or width."
            ),
            "Retransmissions are elevated in the selected interval.",
        ),
        "WIFI_BEACON_LOSS": (
            "warning",
            "Investigate association stability",
            "Check RF coverage, interference and AP logs around the beacon-loss timestamp.",
            "Beacon loss can precede roaming or disassociation events.",
        ),
        "WIFI_NOT_ASSOCIATED": (
            "critical",
            "Restore Wi-Fi association",
            (
                "Confirm the selected interface is connected, the SSID is available "
                "and credentials are valid."
            ),
            (
                "The sensor is not associated with an access point, so Wi-Fi "
                "measurements are incomplete."
            ),
        ),
        "WIFI_TX_FAILURES": (
            "critical",
            "Investigate transmission failures",
            (
                "Check RF interference, AP/client compatibility and driver logs "
                "before changing channel settings."
            ),
            (
                "A high failed-transmission ratio indicates frames are not being "
                "delivered successfully."
            ),
        ),
        "WIFI_ROAM_DETECTED": (
            "info",
            "Correlate the Wi-Fi roam",
            "Compare signal, retries and latency before and after the access-point transition.",
            "A roam can be expected mobility or can coincide with a degraded user experience.",
        ),
        "GATEWAY_ICMP_FAILED": (
            "warning",
            "Validate the local network path",
            "Check the AP uplink, VLAN, gateway ACLs and whether ICMP is intentionally filtered.",
            (
                "The gateway did not answer ICMP; filtering is possible and a "
                "complete outage is not proven."
            ),
        ),
        "GATEWAY_HIGH_PACKET_LOSS": (
            "critical",
            "Investigate the local LAN path",
            "Check AP uplink errors, switch counters, VLAN path and gateway load.",
            "Packet loss to the local gateway affects every downstream test.",
        ),
        "GATEWAY_PACKET_LOSS": (
            "warning",
            "Review local packet loss",
            "Check AP uplink and switch counters, then compare loss with the selected interval.",
            (
                "Packet loss was observed on the local path even though it is "
                "below the critical threshold."
            ),
        ),
        "GATEWAY_HIGH_LATENCY": (
            "warning",
            "Investigate local latency",
            "Check gateway load, wireless contention and AP uplink utilization.",
            "Latency to the local gateway is high for a nearby network hop.",
        ),
        "DNS_FAILURE": (
            "warning",
            "Check DNS reachability and configuration",
            (
                "Verify configured DNS servers, local firewall rules and resolver "
                "response from the same network."
            ),
            "Name resolution failed during the synthetic test.",
        ),
        "HTTPS_FAILURE": (
            "warning",
            "Investigate application reachability",
            (
                "Separate DNS, TLS, proxy and remote-server errors using the "
                "HTTPS status and collector error."
            ),
            "The HTTPS synthetic transaction did not complete successfully.",
        ),
        "DNS_HIGH_LATENCY": (
            "warning",
            "Review DNS response time",
            "Compare configured resolvers and test latency from the same network path.",
            "DNS resolution succeeded but took longer than the expected threshold.",
        ),
        "INTERNET_ICMP_FAILED": (
            "info",
            "Correlate the external ICMP failure",
            (
                "Compare DNS and HTTPS results before changing the local network; "
                "ICMP may be filtered."
            ),
            "External ICMP failed without proving a general Internet outage.",
        ),
        "INTERNET_HIGH_PACKET_LOSS": (
            "critical",
            "Investigate Internet packet loss",
            (
                "Compare gateway and Internet loss to isolate the problem to the "
                "LAN, WAN or destination."
            ),
            "High packet loss was detected toward the external test target.",
        ),
        "INTERNET_PACKET_LOSS": (
            "warning",
            "Review Internet packet loss",
            "Compare local gateway loss with the external target and inspect the upstream path.",
            "Packet loss was detected toward the external test target.",
        ),
        "INTERNET_HIGH_LATENCY": (
            "warning",
            "Investigate Internet latency",
            (
                "Compare gateway latency with the external target to separate local "
                "and upstream delay."
            ),
            "Latency to the external test target is high.",
        ),
        "HTTPS_HIGH_RESPONSE_TIME": (
            "warning",
            "Investigate HTTPS response time",
            "Separate DNS, TLS, proxy and server processing time using the HTTPS timing details.",
            "The HTTPS request completed but exceeded the response-time threshold.",
        ),
        "WIFI_POWER_SAVE_ENABLED": (
            "warning",
            "Review client power saving",
            (
                "Disable Wi-Fi power saving for a dedicated sensor or document "
                "it as a measurement limitation."
            ),
            "Power saving can add latency and affect radio measurements.",
        ),
        "COLLECTION_ERROR": (
            "warning",
            "Fix sensor collection errors",
            (
                "Review Sensor Errors and verify permissions and availability "
                "of iw, ip, ping, nmcli and ethtool."
            ),
            "Some measurements were not collected, so the diagnosis is incomplete.",
        ),
    }

    def build(
        self,
        diagnostic: DiagnosticResult | None,
        calibration: CalibrationResult,
        wifi: WifiMetrics,
        wifi_delta: WifiDeltaMetrics | None,
        connectivity: ConnectivityMetrics,
        environment_changes: list[EnvironmentChange],
    ) -> list[Recommendation]:
        del wifi, wifi_delta, connectivity
        recommendations: list[Recommendation] = []
        seen: set[str] = set()
        findings = diagnostic.findings if diagnostic is not None else []
        for finding in findings:
            guidance = self._GUIDANCE.get(finding.code)
            if guidance is None or finding.code in seen:
                continue
            severity, title, action, rationale = guidance
            recommendations.append(
                Recommendation(
                    code=finding.code,
                    severity=severity,
                    title=title,
                    action=action,
                    rationale=rationale,
                    evidence=finding.message,
                )
            )
            seen.add(finding.code)

        for change in environment_changes:
            if change.code != "WIFI_BSSID_CHANGED" or change.code in seen:
                continue
            recommendations.append(
                Recommendation(
                    code="CORRELATE_AP_CHANGE",
                    severity="info",
                    title="Correlate the access-point change",
                    action=(
                        "Compare RSSI, retries and latency immediately before and "
                        "after the AP change."
                    ),
                    rationale=(
                        "A BSSID change may be normal roaming or may coincide "
                        "with an experience degradation."
                    ),
                    evidence=change.message,
                )
            )
            seen.add(change.code)

        if not calibration.calibrated and not any(
            item.code == "COLLECTION_ERROR" for item in recommendations
        ):
            recommendations.append(
                Recommendation(
                    code="CALIBRATION_INCOMPLETE",
                    severity="info",
                    title="Complete sensor calibration",
                    action=(
                        "Resolve critical checks and review unavailable checks "
                        "before treating a healthy result as conclusive."
                    ),
                    rationale=(
                        "Calibration is incomplete, so the absence of findings "
                        "is not proof that the client is healthy."
                    ),
                    evidence=f"Calibration status: {calibration.status}.",
                )
            )
        return recommendations
