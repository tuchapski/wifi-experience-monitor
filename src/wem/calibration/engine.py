from wem.models.metrics import (
    CalibrationFinding,
    CalibrationResult,
    SensorHealthMetrics,
    TestOutcome,
)


class CalibrationEngine:
    def analyze(
        self,
        health: SensorHealthMetrics,
    ) -> CalibrationResult:
        findings: list[CalibrationFinding] = []

        self._check_interface(
            health,
            findings,
        )

        self._check_driver(
            health,
            findings,
        )

        self._check_rfkill(
            health,
            findings,
        )

        self._check_network_manager(
            health,
            findings,
        )

        self._check_power_save(
            health,
            findings,
        )

        checks = {}
        for name in (
            "interface_exists",
            "interface_up",
            "wireless_interface",
            "driver",
            "firmware_version",
            "rfkill_soft_blocked",
            "rfkill_hard_blocked",
            "network_manager_managed",
            "power_save",
        ):
            value = getattr(health, name)
            if value is None:
                checks[name] = TestOutcome(
                    "unavailable", "The sensor could not determine this value."
                )
            else:
                checks[name] = TestOutcome("observed", str(value))

        status = self._status(findings)
        incomplete = any(check.status == "unavailable" for check in checks.values())
        if incomplete and status not in {"critical", "warning"}:
            status = "inconclusive"

        calibrated = not incomplete and not any(
            finding.severity
            in {
                "critical",
                "warning",
            }
            for finding in findings
        )

        return CalibrationResult(
            status=status,
            checks=checks,
            calibrated=calibrated,
            findings=findings,
        )

    def _check_interface(
        self,
        health: SensorHealthMetrics,
        findings: list[CalibrationFinding],
    ) -> None:
        if health.interface_exists is False:
            findings.append(
                CalibrationFinding(
                    severity="critical",
                    code="INTERFACE_NOT_FOUND",
                    message=("Configured Wi-Fi interface does not exist."),
                )
            )

            return

        if health.interface_up is False:
            findings.append(
                CalibrationFinding(
                    severity="critical",
                    code="INTERFACE_DOWN",
                    message=("Wi-Fi interface is administratively down."),
                )
            )

        if health.wireless_interface is False:
            findings.append(
                CalibrationFinding(
                    severity="critical",
                    code="NOT_WIRELESS_INTERFACE",
                    message=(
                        "Configured interface is not recognized as a wireless interface by iw."
                    ),
                )
            )

    def _check_driver(
        self,
        health: SensorHealthMetrics,
        findings: list[CalibrationFinding],
    ) -> None:
        if health.driver is None:
            findings.append(
                CalibrationFinding(
                    severity="info",
                    code="DRIVER_UNKNOWN",
                    message=("Wi-Fi driver information could not be determined."),
                )
            )

        if health.firmware_version is None:
            findings.append(
                CalibrationFinding(
                    severity="info",
                    code="FIRMWARE_UNKNOWN",
                    message=("Wi-Fi firmware version could not be determined."),
                )
            )

    def _check_rfkill(
        self,
        health: SensorHealthMetrics,
        findings: list[CalibrationFinding],
    ) -> None:
        if health.rfkill_hard_blocked is True:
            findings.append(
                CalibrationFinding(
                    severity="critical",
                    code="RFKILL_HARD_BLOCKED",
                    message=("Wi-Fi radio is hardware blocked."),
                )
            )

        if health.rfkill_soft_blocked is True:
            findings.append(
                CalibrationFinding(
                    severity="critical",
                    code="RFKILL_SOFT_BLOCKED",
                    message=("Wi-Fi radio is software blocked."),
                )
            )

    def _check_network_manager(
        self,
        health: SensorHealthMetrics,
        findings: list[CalibrationFinding],
    ) -> None:
        if health.network_manager_managed is False:
            findings.append(
                CalibrationFinding(
                    severity="info",
                    code="NETWORK_MANAGER_UNMANAGED",
                    message=("Wi-Fi interface is not managed by NetworkManager."),
                )
            )

    def _check_power_save(
        self,
        health: SensorHealthMetrics,
        findings: list[CalibrationFinding],
    ) -> None:
        if health.power_save is True:
            findings.append(
                CalibrationFinding(
                    severity="warning",
                    code="WIFI_POWER_SAVE_ENABLED",
                    message=(
                        "Wi-Fi power saving is enabled. "
                        "For a dedicated monitoring sensor, "
                        "this may influence latency and "
                        "performance measurements."
                    ),
                )
            )

    @staticmethod
    def _status(
        findings: list[CalibrationFinding],
    ) -> str:
        if any(finding.severity == "critical" for finding in findings):
            return "critical"

        if any(finding.severity == "warning" for finding in findings):
            return "warning"

        if findings:
            return "info"

        return "healthy"
