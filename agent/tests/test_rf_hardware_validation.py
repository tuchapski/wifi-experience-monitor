import argparse
import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from wifi_agent.config import AgentSettings
from wifi_agent.core.rf import RfScanResult
from wifi_agent.runtime.rf_scan import RfScanRuntime
from wifi_agent.runtime.rf_sync import RfScanSyncEngine
from wifi_agent.storage import AgentIdentity, RfScanSpool

SCRIPT = Path(__file__).parents[2] / "scripts" / "validate_rf_session.py"
spec = importlib.util.spec_from_file_location("rf_validation", SCRIPT)
assert spec and spec.loader
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
START = datetime(2026, 10, 1, 20, tzinfo=UTC)


def probe_at(second, status="reply", rtt=5):
    return {
        "started_at": (START + timedelta(seconds=second)).isoformat(),
        "ended_at": (START + timedelta(seconds=second + 0.1)).isoformat(),
        "status": status,
        "rtt_ms": rtt if status == "reply" else None,
    }


def scan_at(second, duration=1000, interface="wlan0"):
    return {
        "scan_id": f"rfs_{second}",
        "interface": interface,
        "observed_at": (START + timedelta(seconds=second)).isoformat(),
        "duration_ms": duration,
    }


def test_tool_errors_are_not_packet_loss_and_unknown_rtt_stays_null():
    result = validation.statistics(
        [probe_at(1, "tool_error"), probe_at(2, "no_reply"), probe_at(3, rtt=0)]
    )
    assert result["tool_errors"] == 1
    assert result["no_reply_percent"] == 50
    assert result["rtt_mean_ms"] == 0
    empty = validation.statistics([probe_at(1, "tool_error")])
    assert empty["no_reply_percent"] is None
    assert empty["rtt_p95_ms"] is None


def test_scan_window_uses_completion_minus_duration_and_keeps_outside_range_unknown():
    result = validation.compare_scan_windows(
        [probe_at(8), probe_at(9.5), probe_at(15), probe_at(19.5, "no_reply"), probe_at(21)],
        [scan_at(20), scan_at(10), scan_at(12, interface="wlan1")],
        "wlan0",
    )
    groups = result["groups"]
    assert result["successful_scans_used"] == 2
    assert groups["overlapping"]["probes"] == 2
    assert groups["overlapping"]["no_reply_percent"] == 50
    assert groups["other_in_evidence_range"]["probes"] == 1
    assert groups["unclassified"]["probes"] == 2


def test_no_scans_does_not_claim_scan_free_baseline():
    result = validation.compare_scan_windows([probe_at(10)], [], "wlan0")
    assert result["groups"]["unclassified"]["probes"] == 1
    assert result["groups"]["other_in_evidence_range"]["probes"] == 0


def test_invalid_windows_duplicates_and_overlapping_scans():
    result = validation.compare_scan_windows(
        [probe_at(8.5)],
        [scan_at(10, duration=3000), scan_at(10), scan_at(9), scan_at(12, duration=-1)],
        "wlan0",
    )
    assert result["successful_scans_used"] == 2
    assert result["invalid_scan_windows"] == 1
    assert result["groups"]["overlapping"]["probes"] == 1


def test_backwards_probe_clock_is_not_silently_compared():
    sample = probe_at(10)
    sample["ended_at"] = START.isoformat()
    with pytest.raises(ValueError, match="clock moved backwards"):
        validation.compare_scan_windows([sample], [], "wlan0")


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_capture_duration_is_rejected(value):
    with pytest.raises(argparse.ArgumentTypeError, match="finite number"):
        validation.positive(value)


def test_ping_distinguishes_reply_no_reply_permission_error_and_timeout(monkeypatch):
    command = Mock()
    monkeypatch.setattr(validation.subprocess, "run", command)
    command.return_value = SimpleNamespace(returncode=0, stdout="time=0.5 ms", stderr="")
    assert validation.probe("wlan0", "192.0.2.1")["rtt_ms"] == 0.5
    assert command.call_args.args[0][3:5] == ["wlan0", "-c"]
    command.return_value = SimpleNamespace(returncode=1, stdout="", stderr="")
    assert validation.probe("wlan0", "192.0.2.1")["status"] == "no_reply"
    command.return_value = SimpleNamespace(
        returncode=2, stdout="", stderr="Operation not permitted"
    )
    assert validation.probe("wlan0", "192.0.2.1")["status"] == "tool_error"
    command.side_effect = subprocess.TimeoutExpired("ping", 2)
    assert validation.probe("wlan0", "192.0.2.1")["status"] == "tool_error"


def test_report_has_no_hardware_pass_and_preserves_partial_scan_coverage(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "interface": "wlan0",
                "hardware": {"hostname": "sensor.example"},
                "interrupted": False,
            }
        )
    )
    (tmp_path / "probes.jsonl").write_text(json.dumps(probe_at(9.5)) + "\n")
    api = Mock(
        side_effect=[
            {"agent_id": "agt_1", "status": "completed", "sync_status": "synced"},
            {"hostname": "sensor"},
            {"scan_count": 2501},
            [scan_at(10)],
        ]
    )
    monkeypatch.setattr(validation, "get_json", api)
    validation.report(SimpleNamespace(input=tmp_path, recording_id="rec_1", server="http://local"))
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["scan_windows_complete"] is False
    assert report["hardware_validation"] == "pending_review"
    assert report["recording_rf_summary"]["scan_count"] == 2501


def test_report_refuses_comparison_between_different_hosts(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "interface": "wlan0",
                "hardware": {"hostname": "other-host"},
            }
        )
    )
    (tmp_path / "probes.jsonl").write_text("")
    monkeypatch.setattr(
        validation,
        "get_json",
        Mock(
            side_effect=[
                {"agent_id": "agt_1"},
                {"hostname": "sensor"},
            ]
        ),
    )
    with pytest.raises(ValueError, match="different hosts"):
        validation.report(
            SimpleNamespace(input=tmp_path, recording_id="rec_1", server="http://local")
        )


def test_three_hour_rf_backlog_survives_reopen_retention_and_lost_ack(tmp_path):
    """Simulated elapsed time: real SQLite and replay behavior, no radio/hardware claim."""
    path = tmp_path / "agent.db"
    spool = RfScanSpool(path)
    spool.initialize()
    for minute in range(180):
        spool.enqueue(
            RfScanResult(
                interface="wlan0",
                observed_at=START + timedelta(minutes=minute),
                duration_ms=100,
                recording_id="rec_soak",
            )
        )
    original = spool.pending(limit=200)
    spool = RfScanSpool(path)
    spool.initialize()
    assert spool.prune_before(datetime.now(UTC) + timedelta(days=2)) == 0
    assert [item.scan_id for item in spool.pending(limit=200)] == [
        item.scan_id for item in original
    ]
    identity = AgentIdentity(
        agent_id="agt_1",
        agent_token="test",
        server_url="http://local",
        enrolled_at=START,
    )
    engine = RfScanSyncEngine(Mock(spec=AgentSettings), identity, spool)
    received = set()
    replayed = []
    lose_ack = True

    def publish(_identity, scan):
        nonlocal lose_ack
        replay = scan.scan_id in received
        received.add(scan.scan_id)
        if lose_ack:
            lose_ack = False
            raise OSError("acknowledgement lost after server accepted scan")
        if replay:
            replayed.append(scan.scan_id)
        return {"status": "already_accepted" if replay else "accepted"}

    engine.client = Mock()
    engine.client.publish_rf_scan.side_effect = publish
    assert engine.sync_pending() == 0
    assert spool.pending_count() == 180
    total = 0
    while spool.pending_count():
        total += engine.sync_pending()
    assert total == len(received) == 180
    assert replayed == [original[0].scan_id]
    next_scan = spool.enqueue(RfScanResult(interface="wlan0", observed_at=START, duration_ms=1))
    assert next_scan is not None and next_scan.sequence == 181


def test_capture_writes_evidence_and_refuses_to_overwrite_previous_run(tmp_path, monkeypatch):
    monkeypatch.setattr(validation.shutil, "which", lambda _: "/usr/bin/ping")
    monkeypatch.setattr(validation, "hardware", lambda _: {"hostname": "sensor", "driver": None})
    monkeypatch.setattr(validation, "probe", lambda *_: probe_at(1, "no_reply"))
    output = tmp_path / "capture"
    args = SimpleNamespace(interface="lo", target="127.0.0.1", minutes=0.0001, output=output)
    validation.capture(args)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["probes"] == 1
    assert manifest["interrupted"] is False
    assert json.loads((output / "probes.jsonl").read_text())["status"] == "no_reply"
    with pytest.raises(FileExistsError):
        validation.capture(args)


def test_scan_worker_remains_nonblocking_during_a_slow_radio_scan():
    entered, release = Event(), Event()
    runtime = RfScanRuntime("wlan0", interval_seconds=60)
    result = RfScanResult(interface="wlan0", observed_at=START, duration_ms=5000)

    def collect():
        entered.set()
        assert release.wait(5)
        return result

    runtime.collector.collect = collect
    try:
        assert runtime.maybe_start(0)
        assert entered.wait(2)
        pending = runtime._pending
        assert pending is not None
        for second in range(1, 120):
            assert runtime.poll() is None
            assert runtime.maybe_start(second) is False
            values = {item.metric: item.value for item in runtime.readiness_observations(START)}
            assert values["wifi.scan_running"] is True
            assert values["wifi.scan_status"] == "pending"
        release.set()
        assert pending.result(timeout=2) is result
        assert runtime.poll() is result
    finally:
        release.set()
        runtime.close()
