from wifi_server.analysis.current_link import score_link


def test_full_link_score_explains_weighted_metrics() -> None:
    result = score_link(
        {
            "connected": True,
            "rssi_dbm": -75,
            "tx_retries_per_100_packets": 20,
            "tx_failed_percent": 5,
        },
        [],
    )

    assert result["value"] == 62.5
    assert result["status"] == "measured"
    assert result["coverage_percent"] == 100
    assert [item["score"] for item in result["components"]] == [70, 70, 20]


def test_link_score_requires_rssi_and_marks_partial_counters() -> None:
    provisional = score_link({"connected": True, "rssi_dbm": -75}, [])
    unavailable = score_link({"connected": True, "tx_retries_per_100_packets": 5}, [])

    assert provisional["value"] == 70
    assert provisional["coverage_percent"] == 60
    assert provisional["status"] == "provisional"
    assert unavailable["value"] is None
    assert unavailable["status"] == "unavailable"


def test_link_score_disconnection_is_explicit_and_ignores_stale_readings() -> None:
    result = score_link({"connected": False, "rssi_dbm": -55, "tx_failed_percent": 1}, [])

    assert result["status"] == "disconnected"
    assert result["value"] == 0
    assert result["coverage_percent"] == 0
    assert all(item["reading"] is None for item in result["components"])


def test_invalid_values_and_collector_error_cannot_look_measured() -> None:
    invalid = score_link({"connected": True, "rssi_dbm": float("nan")}, [])
    warning = score_link(
        {
            "connected": True,
            "rssi_dbm": -67,
            "tx_retries_per_100_packets": 0,
            "tx_failed_percent": 0,
        },
        ["survey collector failed"],
    )

    assert invalid["value"] is None
    assert warning["value"] == 100
    assert warning["status"] == "provisional"
