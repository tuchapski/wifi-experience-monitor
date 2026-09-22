from wem.analysis.service_slo_stats import summarize_service_executions


def payload(
    service: str,
    status: str,
    *,
    fresh: bool = True,
    latency: float | None = None,
    packet_loss: float | None = None,
) -> dict[str, object]:
    connectivity: dict[str, object] = {
        "tests": {service: {"status": status, "fresh": fresh}},
    }
    if service == "gateway":
        connectivity["gateway_latency_avg_ms"] = latency
        connectivity["gateway_packet_loss_percent"] = packet_loss
    elif service == "internet":
        connectivity["internet_latency_avg_ms"] = latency
        connectivity["internet_packet_loss_percent"] = packet_loss
    elif service == "dns":
        connectivity["dns_latency_ms"] = latency
    elif service == "https":
        connectivity["https_total_time_ms"] = latency
    return {"connectivity": connectivity}


def test_history_summary_counts_only_fresh_executions():
    result = summarize_service_executions(
        [
            payload("gateway", "passed", latency=10.0, packet_loss=0.0),
            payload("gateway", "passed", latency=20.0, packet_loss=1.0),
            payload("gateway", "failed", packet_loss=100.0),
            payload("gateway", "error"),
            payload("gateway", "passed", fresh=False, latency=9999.0, packet_loss=100.0),
        ]
    )

    gateway = result["gateway"]
    assert gateway["attempt_count"] == 4
    assert gateway["measurable_count"] == 3
    assert gateway["success_count"] == 2
    assert gateway["failure_count"] == 1
    assert gateway["measurement_error_count"] == 1
    assert gateway["availability_percent"] == 66.667
    assert gateway["latency_ms"]["p50"] == 15.0
    assert gateway["packet_loss_percent"]["p95"] == 90.1


def test_history_summary_preserves_missing_data():
    result = summarize_service_executions([])
    dns = result["dns"]

    assert dns["attempt_count"] == 0
    assert dns["availability_percent"] is None
    assert dns["latency_ms"]["p95"] is None
