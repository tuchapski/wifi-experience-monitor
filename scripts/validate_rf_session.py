#!/usr/bin/env python3
"""Capture ICMP evidence and compare it with stored, successful RF scan windows."""

import argparse
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import subprocess
import time
from bisect import bisect_right
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Evidence timestamps must include a timezone")
    return result


def positive(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("Use a finite number greater than zero")
    return parsed


def probe(interface: str, target: str) -> dict:
    started_at = utc_now()
    started = time.monotonic()
    status, rtt, error = "tool_error", None, None
    try:
        result = subprocess.run(
            ["ping", "-n", "-I", interface, "-c", "1", "-W", "1", target],
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, "LC_ALL": "C"},
            check=False,
        )
        match = re.search(r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms", result.stdout)
        if result.returncode == 0 and match:
            rtt = float(match.group(1))
            if math.isfinite(rtt) and rtt >= 0:
                status = "reply"
        elif result.returncode == 1:
            status = "no_reply"
        if status == "tool_error":
            error = (result.stderr.strip() or "ping did not return a usable result")[:300]
    except (OSError, subprocess.TimeoutExpired) as exc:
        error = str(exc)[:300]
    return {
        "started_at": started_at,
        "ended_at": utc_now(),
        "duration_seconds": time.monotonic() - started,
        "status": status,
        "rtt_ms": rtt if status == "reply" else None,
        "error": error,
    }


def hardware(interface: str) -> dict:
    device = Path("/sys/class/net") / interface / "device"
    driver = device / "driver"
    return {
        "hostname": socket.gethostname(),
        "kernel": os.uname().release,
        "driver": driver.resolve().name if driver.is_symlink() else None,
        "pci_vendor": (device / "vendor").read_text().strip()
        if (device / "vendor").exists()
        else None,
        "pci_device": (device / "device").read_text().strip()
        if (device / "device").exists()
        else None,
    }


def capture(args: argparse.Namespace) -> None:
    if not shutil.which("ping"):
        raise ValueError("ping is missing; install iputils-ping")
    if not (Path("/sys/class/net") / args.interface).is_dir():
        raise ValueError(f"Interface not found: {args.interface}")
    target = str(ipaddress.ip_address(args.target))
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "interface": args.interface,
        "target": target,
        "requested_minutes": args.minutes,
        "probe_interval_seconds": 1,
        "started_at": utc_now(),
        "hardware": hardware(args.interface),
        "interrupted": False,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Capturing on {args.interface} to {target}; Ctrl+C saves a partial capture.", flush=True)
    start = next_probe = time.monotonic()
    count = 0
    try:
        with (args.output / "probes.jsonl").open("w") as stream:
            while time.monotonic() - start < args.minutes * 60:
                stream.write(json.dumps(probe(args.interface, target)) + "\n")
                stream.flush()
                count += 1
                next_probe = max(next_probe + 1, time.monotonic())
                delay = min(
                    next_probe - time.monotonic(), start + args.minutes * 60 - time.monotonic()
                )
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        manifest["interrupted"] = True
    finally:
        manifest.update(ended_at=utc_now(), elapsed_seconds=time.monotonic() - start, probes=count)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Saved {count} probes to {args.output}")


def statistics(probes: list[dict]) -> dict:
    replies = sorted(p["rtt_ms"] for p in probes if p["status"] == "reply")
    no_reply = sum(p["status"] == "no_reply" for p in probes)
    usable = len(replies) + no_reply
    return {
        "probes": len(probes),
        "replies": len(replies),
        "no_reply": no_reply,
        "tool_errors": len(probes) - usable,
        "no_reply_percent": 100 * no_reply / usable if usable else None,
        "rtt_mean_ms": sum(replies) / len(replies) if replies else None,
        "rtt_p95_ms": replies[math.ceil(len(replies) * 0.95) - 1] if replies else None,
        "rtt_max_ms": replies[-1] if replies else None,
    }


def compare_scan_windows(probes: list[dict], scans: list[dict], interface: str) -> dict:
    windows = []
    invalid = 0
    seen = set()
    for scan in scans:
        if scan.get("interface") != interface or scan.get("scan_id") in seen:
            continue
        try:
            end = timestamp(scan["observed_at"])
            duration = float(scan["duration_ms"])
            if not math.isfinite(duration) or duration < 0:
                raise ValueError("Invalid scan duration")
            windows.append((end - timedelta(milliseconds=duration), end))
            seen.add(scan["scan_id"])
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid += 1
    windows.sort()
    merged = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    starts = [window[0] for window in merged]
    groups: dict[str, list[dict]] = {
        "overlapping": [],
        "other_in_evidence_range": [],
        "unclassified": [],
    }
    for sample in probes:
        start, end = timestamp(sample["started_at"]), timestamp(sample["ended_at"])
        if end < start:
            raise ValueError("Probe clock moved backwards; capture cannot be compared")
        index = bisect_right(starts, end) - 1
        if index >= 0 and merged[index][1] >= start:
            group = "overlapping"
        elif merged and start >= merged[0][0] and end <= merged[-1][1]:
            group = "other_in_evidence_range"
        else:
            group = "unclassified"
        groups[group].append(sample)
    return {
        "successful_scans_used": len(windows),
        "invalid_scan_windows": invalid,
        "groups": {name: statistics(samples) for name, samples in groups.items()},
        "interpretation": (
            "Overlap uses each probe execution interval and scan completion minus duration. "
            "Only successful stored scans are visible. Other probes are not a scan-free baseline. "
            "Sampling, clock adjustments, failed scans and delayed uploads limit comparison. "
            "This is temporal association, not evidence that scans caused a problem."
        ),
    }


def get_json(server: str, path: str):
    with urlopen(server.rstrip("/") + "/api/v1" + path, timeout=15) as response:
        return json.load(response)


def report(args: argparse.Namespace) -> None:
    manifest = json.loads((args.input / "manifest.json").read_text())
    probes = [
        json.loads(line) for line in (args.input / "probes.jsonl").read_text().splitlines() if line
    ]
    for sample in probes:
        if sample.get("status") not in {"reply", "no_reply", "tool_error"}:
            raise ValueError("Unknown probe outcome")
        if sample["status"] == "reply" and (
            not isinstance(sample.get("rtt_ms"), (int, float))
            or not math.isfinite(sample["rtt_ms"])
            or sample["rtt_ms"] < 0
        ):
            raise ValueError("Invalid reply RTT")
    path = "/recordings/" + quote(args.recording_id, safe="")
    recording = get_json(args.server, path)
    agent = get_json(args.server, "/agents/" + quote(recording["agent_id"], safe=""))
    captured_host = manifest["hardware"]["hostname"].split(".")[0].casefold()
    if captured_host != agent["hostname"].split(".")[0].casefold():
        raise ValueError("Recording Agent and ping capture belong to different hosts")
    summary = get_json(args.server, path + "/rf/summary")
    scans = get_json(args.server, path + "/rf/scans?limit=2000")
    comparison = compare_scan_windows(probes, scans, manifest["interface"])
    used = comparison["successful_scans_used"]
    result = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "capture": manifest,
        "recording_id": args.recording_id,
        "recording_status": recording["status"],
        "sync_status": recording["sync_status"],
        "recording_rf_summary": summary,
        "scan_windows_complete": used > 0 and used == summary["scan_count"],
        "probes": statistics(probes),
        "scan_comparison": comparison,
        "hardware_validation": "pending_review",
        "notes": [
            "This tool does not declare a hardware PASS or infer congestion/interference.",
            "The RF summary covers all stored scans; impact windows use at most the latest 2000.",
            "Finish the recording and wait for uploads before producing the final report.",
            "No-reply includes ICMP loss, unreachable destinations and target behavior.",
        ],
    }
    destination = args.input / "report.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"report": str(destination), "probes": result["probes"], "scans_used": used}, indent=2
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser(
        "capture", help="Read-only ICMP probe capture on the laptop"
    )
    capture_parser.add_argument("--interface", required=True)
    capture_parser.add_argument(
        "--target", required=True, help="IP of an ICMP-responsive host on the office LAN"
    )
    capture_parser.add_argument("--minutes", type=positive, default=60)
    capture_parser.add_argument("--output", type=Path, required=True)
    report_parser = commands.add_parser(
        "report", help="Compare capture with existing recording RF evidence"
    )
    report_parser.add_argument("--server", default="http://127.0.0.1:8000")
    report_parser.add_argument("--recording-id", required=True)
    report_parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        (capture if args.command == "capture" else report)(args)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"RF validation error: {exc}\n")


if __name__ == "__main__":
    main()
