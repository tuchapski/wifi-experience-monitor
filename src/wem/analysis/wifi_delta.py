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

        if self._association_changed(previous, current):
            result.association_changed = True
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
            return result

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
