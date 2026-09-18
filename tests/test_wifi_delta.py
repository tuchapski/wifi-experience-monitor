from wem.analysis.wifi_delta import WifiDeltaAnalyzer
from wem.models.metrics import WifiMetrics


def create_wifi_metrics(
    *,
    bssid: str = "98:7e:ca:8a:3e:0e",
    tx_packets: int = 1000,
    tx_retries: int = 100,
    tx_failed: int = 2,
    rx_packets: int = 2000,
    rx_drop_misc: int = 10,
) -> WifiMetrics:
    return WifiMetrics(
        interface="wlp0s20f3",
        bssid=bssid,
        tx_packets=tx_packets,
        tx_retries=tx_retries,
        tx_failed=tx_failed,
        rx_packets=rx_packets,
        rx_drop_misc=rx_drop_misc,
    )


def test_wifi_delta_calculation() -> None:
    previous = create_wifi_metrics()

    current = create_wifi_metrics(
        tx_packets=1200,
        tx_retries=130,
        tx_failed=3,
        rx_packets=2400,
        rx_drop_misc=14,
    )

    analyzer = WifiDeltaAnalyzer()

    result = analyzer.calculate(
        previous,
        current,
        interval_seconds=10.0,
    )

    assert result.interval_seconds == 10.0

    assert result.tx_packets_delta == 200
    assert result.tx_retries_delta == 30
    assert result.tx_failed_delta == 1

    assert result.rx_packets_delta == 400
    assert result.rx_drop_misc_delta == 4

    assert result.tx_retries_per_100_packets == 15.0
    assert result.tx_failed_percent == 0.5
    assert result.rx_drop_percent == 1.0

    assert result.association_changed is False
    assert result.counter_reset_detected is False


def test_wifi_delta_detects_association_change() -> None:
    previous = create_wifi_metrics(
        bssid="98:7e:ca:8a:3e:0e",
    )

    current = create_wifi_metrics(
        bssid="aa:bb:cc:dd:ee:ff",
        tx_packets=1200,
    )

    analyzer = WifiDeltaAnalyzer()

    result = analyzer.calculate(
        previous,
        current,
        interval_seconds=10.0,
    )

    assert result.association_changed is True

    assert result.tx_packets_delta is None
    assert result.tx_retries_delta is None


def test_wifi_delta_detects_counter_reset() -> None:
    previous = create_wifi_metrics(
        tx_packets=5000,
    )

    current = create_wifi_metrics(
        tx_packets=100,
    )

    analyzer = WifiDeltaAnalyzer()

    result = analyzer.calculate(
        previous,
        current,
        interval_seconds=10.0,
    )

    assert result.counter_reset_detected is True

    assert result.tx_packets_delta is None


def test_wifi_delta_handles_missing_counter() -> None:
    previous = create_wifi_metrics()

    current = create_wifi_metrics()
    current.tx_retries = None

    analyzer = WifiDeltaAnalyzer()

    result = analyzer.calculate(
        previous,
        current,
        interval_seconds=10.0,
    )

    assert result.tx_packets_delta == 0
    assert result.tx_retries_delta is None

    assert result.tx_retries_per_100_packets is None
