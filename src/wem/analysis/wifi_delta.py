import math

from wem.models.metrics import WifiDeltaMetrics, WifiMetrics


class WifiDeltaAnalyzer:
    def calculate(
        self,
        previous: WifiMetrics,
        current: WifiMetrics,
        interval_seconds: float,
    ) -> WifiDeltaMetrics:
        result = WifiDeltaMetrics(
            interval_seconds=interval_seconds,
        )

        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            result.unavailable_reason = "Invalid measurement interval."
            return result
        if previous.interface != current.interface:
            result.unavailable_reason = (
                "Selected interface changed; waiting for comparable samples."
            )
            return result
        if (
            previous.associated is False
            or current.associated is False
            or previous.bssid is None
            or current.bssid is None
        ):
            result.unavailable_reason = "Association could not be confirmed across both samples."
            return result
        if self._association_changed(previous, current):
            result.association_changed = True
            result.unavailable_reason = "Access point changed; waiting for comparable samples."
            return result

        if (
            previous.connected_time_seconds is not None
            and current.connected_time_seconds is not None
            and current.connected_time_seconds < previous.connected_time_seconds
        ):
            result.counter_reset_detected = True
            result.unavailable_reason = (
                "Association duration restarted; counters are not comparable."
            )
            return result

        tx_packets = self._delta(
            previous.tx_packets,
            current.tx_packets,
        )

        tx_retries = self._delta(
            previous.tx_retries,
            current.tx_retries,
        )

        tx_failed = self._delta(
            previous.tx_failed,
            current.tx_failed,
        )

        rx_packets = self._delta(
            previous.rx_packets,
            current.rx_packets,
        )

        rx_drop_misc = self._delta(
            previous.rx_drop_misc,
            current.rx_drop_misc,
        )

        deltas = [
            tx_packets,
            tx_retries,
            tx_failed,
            rx_packets,
            rx_drop_misc,
        ]

        if any(delta == -1 for delta in deltas):
            result.counter_reset_detected = True
            result.unavailable_reason = "Counters reset; waiting for comparable samples."
            return result

        self._calculate_survey(previous, current, result)

        result.tx_packets_delta = tx_packets
        result.tx_retries_delta = tx_retries
        result.tx_failed_delta = tx_failed

        result.rx_packets_delta = rx_packets
        result.rx_drop_misc_delta = rx_drop_misc

        if tx_packets is not None and tx_packets > 0 and tx_retries is not None:
            result.tx_retries_per_100_packets = round(
                (tx_retries / tx_packets) * 100,
                3,
            )

        if tx_packets is not None and tx_packets > 0 and tx_failed is not None:
            result.tx_failed_percent = round(
                (tx_failed / tx_packets) * 100,
                3,
            )

        if rx_packets is not None and rx_packets > 0 and rx_drop_misc is not None:
            result.rx_drop_percent = round(
                (rx_drop_misc / rx_packets) * 100,
                3,
            )

        return result

    @staticmethod
    def _calculate_survey(
        previous: WifiMetrics, current: WifiMetrics, result: WifiDeltaMetrics
    ) -> None:
        before, after = previous.survey, current.survey
        if (
            before.status not in {"available", "partial"}
            or after.status not in {"available", "partial"}
            or before.frequency_mhz is None
            or before.frequency_mhz != after.frequency_mhz
            or before.frequency_mhz != previous.frequency_mhz
            or after.frequency_mhz != current.frequency_mhz
            or previous.channel_width_mhz is None
            or previous.channel_width_mhz != current.channel_width_mhz
        ):
            result.survey_unavailable_reason = (
                "Two surveys of the same operating channel and width are required."
            )
            return
        if before.active_ms is None or after.active_ms is None:
            result.survey_unavailable_reason = "Channel active-time counters unavailable."
            return
        counters = ("active_ms", "busy_ms", "rx_ms", "tx_ms")
        for name in counters:
            start, end = getattr(before, name), getattr(after, name)
            if start is not None and end is not None and end < start:
                result.survey_unavailable_reason = (
                    "Survey counters reset; waiting for comparable samples."
                )
                return
        active = after.active_ms - before.active_ms
        if active <= 0:
            result.survey_unavailable_reason = "No positive channel active-time delta."
            return
        result.survey_active_ms_delta = active
        missing = []
        for name, destination in (
            ("busy_ms", "channel_utilization_percent"),
            ("rx_ms", "channel_rx_percent"),
            ("tx_ms", "channel_tx_percent"),
        ):
            start, end = getattr(before, name), getattr(after, name)
            if start is None or end is None:
                missing.append(name)
                continue
            difference = end - start
            if difference > active:
                missing.append(name)
                continue
            setattr(result, destination, round(100 * difference / active, 3))
        if missing:
            result.survey_unavailable_reason = (
                "Unavailable or inconsistent interval counters: " + ", ".join(missing) + "."
            )

    @staticmethod
    def _delta(
        previous: int | None,
        current: int | None,
    ) -> int | None:
        if previous is None or current is None:
            return None

        if current < previous:
            return -1

        return current - previous

    @staticmethod
    def _association_changed(
        previous: WifiMetrics,
        current: WifiMetrics,
    ) -> bool:
        if previous.bssid is None or current.bssid is None:
            return False

        return previous.bssid != current.bssid
