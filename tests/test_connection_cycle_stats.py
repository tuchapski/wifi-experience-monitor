from wem.analysis.connection_cycle_stats import summarize_connection_cycles


def test_connection_cycle_summary_preserves_missing_values_and_percentiles() -> None:
    cycles: list[dict[str, object]] = [
        {
            "session_id": "one",
            "session_type": "initial_connect",
            "state": "ready",
            "total_time_ms": 1000.0,
            "timing_source": "networkmanager_dbus+sampling",
            "stages": {
                "association": {
                    "elapsed_ms": 100.0,
                    "source": "networkmanager_dbus",
                },
                "network_ready": {"elapsed_ms": 1000.0, "source": "sampling"},
            },
        },
        {
            "session_id": "two",
            "session_type": "reconnect",
            "state": "ready",
            "total_time_ms": 3000.0,
            "timing_source": "sampling",
            "stages": {
                "association": {"elapsed_ms": 500.0, "source": "sampling"},
                "network_ready": {"elapsed_ms": 3000.0, "source": "sampling"},
            },
        },
        {
            "session_id": "three",
            "session_type": "observed_existing",
            "state": "ready",
            "total_time_ms": None,
            "timing_source": "sampling",
            "stages": {
                "association": {"elapsed_ms": None, "source": "sampling"},
            },
        },
    ]

    summary = summarize_connection_cycles(cycles)

    assert summary["total_cycles"] == 3
    assert summary["ready_cycles"] == 3
    assert summary["measurable_cycles"] == 2
    assert summary["unmeasured_cycles"] == 1
    assert summary["by_type"] == {
        "initial_connect": 1,
        "observed_existing": 1,
        "reconnect": 1,
    }

    total = summary["total_time_ms"]
    assert isinstance(total, dict)
    assert total["count"] == 2
    assert total["p50"] == 2000.0
    assert total["p95"] == 2900.0
    assert total["p99"] == 2980.0

    stages = summary["stages"]
    assert isinstance(stages, dict)
    association = stages["association"]
    assert isinstance(association, dict)
    assert association["count"] == 2
    assert association["p50"] == 300.0
    assert association["sources"] == {"networkmanager_dbus": 1, "sampling": 1}


def test_connection_cycle_summary_handles_empty_history() -> None:
    summary = summarize_connection_cycles([])

    assert summary["total_cycles"] == 0
    assert summary["measurable_cycles"] == 0
    total = summary["total_time_ms"]
    assert isinstance(total, dict)
    assert total["count"] == 0
    assert total["p95"] is None
