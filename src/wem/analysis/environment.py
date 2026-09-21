from wem.models.metrics import EnvironmentChange, WifiMetrics


class EnvironmentChangeAnalyzer:
    """Find meaningful association and radio changes between samples.

    Unknown values are deliberately ignored. A value becoming known after a
    collector failure is not evidence that the environment changed.
    """

    _FIELDS: tuple[tuple[str, str, str], ...] = (
        ("ssid", "SSID", "SSID changed"),
        ("bssid", "BSSID", "Access point changed"),
        ("frequency_mhz", "frequency_mhz", "Operating frequency changed"),
        ("channel", "channel", "Wi-Fi channel changed"),
        ("channel_width_mhz", "channel_width_mhz", "Channel width changed"),
        ("tx_phy_mode", "TX PHY", "TX PHY mode changed"),
        ("rx_phy_mode", "RX PHY", "RX PHY mode changed"),
    )

    def compare(
        self,
        previous: WifiMetrics,
        current: WifiMetrics,
    ) -> list[EnvironmentChange]:
        if previous.interface != current.interface:
            return []

        changes: list[EnvironmentChange] = []
        for attribute, field, message in self._FIELDS:
            old = getattr(previous, attribute)
            new = getattr(current, attribute)
            if old is None or new is None or old == new:
                continue
            changes.append(
                EnvironmentChange(
                    code=f"WIFI_{field.upper().replace(' ', '_')}_CHANGED",
                    field=field,
                    previous=old,
                    current=new,
                    message=f"{message}: {old} → {new}.",
                )
            )

        if previous.associated is not None and current.associated is not None:
            if previous.associated != current.associated:
                state = "associated" if current.associated else "disconnected"
                changes.append(
                    EnvironmentChange(
                        code="WIFI_ASSOCIATION_STATE_CHANGED",
                        field="association",
                        previous=previous.associated,
                        current=current.associated,
                        message=f"Wi-Fi association state changed; current state is {state}.",
                    )
                )

        return changes
