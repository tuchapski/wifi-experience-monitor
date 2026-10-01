"""Summarize all stored recording scans with a streaming query and no causal claims."""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import groupby
from math import isfinite

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.db.models import AgentRfBssObservation, AgentRfScan, DiagnosticRecording
from wifi_server.rf_summary_schemas import RecordingRfSummary, RfSampleStatistics

STRONG_NEIGHBOR_THRESHOLD_DBM = -70.0


@dataclass
class _Statistics:
    count: int = 0
    total: float = 0
    minimum: float | None = None
    maximum: float | None = None

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def response(self) -> RfSampleStatistics:
        return RfSampleStatistics(
            sample_count=self.count,
            minimum=self.minimum,
            average=self.total / self.count if self.count else None,
            maximum=self.maximum,
        )


def _signal(value: float | None) -> bool:
    return value is not None and isfinite(value)


def summarize_rf_rows(rows: Iterable[tuple]) -> RecordingRfSummary:
    """Rows ordered by scan time/id; only one scan's BSS data is buffered at a time.

    An outer-join row with no BSSID represents a successful scan with zero BSS.
    Association transitions require consecutive scans on the same interface with
    exactly one associated BSS. Missing or ambiguous association breaks continuity.
    """
    visible, same_channel, same_ssid, strong, delta = (_Statistics() for _ in range(5))
    unique_bss: set[str] = set()
    unique_ssids: set[str] = set()
    scans = observations = associated_scans = stronger_scans = 0
    association_pairs = bssid_changes = frequency_changes = 0
    neighborhood_pairs = neighborhood_changes = additions = removals = 0
    first_at = last_at = previous_at = None
    previous_interface = None
    previous_associated = None
    previous_visible = None
    maximum_gap = None

    for _, scan_rows in groupby(rows, key=lambda row: row[0]):
        snapshot = list(scan_rows)
        _, observed_at, interface, *_ = snapshot[0]
        bsses = {row[3].strip().lower(): row for row in snapshot if row[3]}
        ids = set(bsses)
        unique_bss.update(ids)
        unique_ssids.update(row[4] for row in bsses.values() if row[4])
        scans += 1
        observations += len(bsses)
        first_at = first_at or observed_at
        last_at = observed_at
        if previous_at is not None:
            gap = (observed_at - previous_at).total_seconds()
            maximum_gap = gap if maximum_gap is None else max(maximum_gap, gap)
        associated_rows = [(bssid, row) for bssid, row in bsses.items() if row[8]]
        associated = associated_rows[0] if len(associated_rows) == 1 else None
        neighbors = {bssid: row for bssid, row in bsses.items() if not row[8]}
        visible.add(len(neighbors))
        # Missing RSSI cannot certify the count of strong neighbors for this scan.
        if all(_signal(row[7]) for row in neighbors.values()):
            strong.add(sum(row[7] >= STRONG_NEIGHBOR_THRESHOLD_DBM for row in neighbors.values()))
        if associated is not None:
            associated_scans += 1
            _, current = associated
            if current[5] is not None:
                same_channel.add(sum(row[5] == current[5] for row in neighbors.values()))
            if current[4]:
                alternatives = [row for row in neighbors.values() if row[4] == current[4]]
                same_ssid.add(len(alternatives))
                if (
                    alternatives
                    and _signal(current[7])
                    and all(_signal(row[7]) for row in alternatives)
                ):
                    difference = max(row[7] for row in alternatives) - current[7]
                    delta.add(difference)
                    stronger_scans += int(difference > 0)

        if previous_interface == interface:
            if previous_visible is not None:
                neighborhood_pairs += 1
                neighborhood_changes += int(previous_visible != ids)
                additions += len(ids - previous_visible)
                removals += len(previous_visible - ids)
            if associated is not None and previous_associated is not None:
                association_pairs += 1
                bssid_changes += int(associated[0] != previous_associated[0])
                previous_frequency, current_frequency = previous_associated[1][5], associated[1][5]
                if previous_frequency is not None and current_frequency is not None:
                    frequency_changes += int(previous_frequency != current_frequency)
        previous_at = observed_at
        previous_interface = interface
        previous_associated = associated
        previous_visible = ids

    return RecordingRfSummary(
        scan_count=scans,
        total_bss_observations=observations,
        unique_bss=len(unique_bss),
        unique_ssids=len(unique_ssids),
        first_scan_at=first_at,
        last_scan_at=last_at,
        maximum_scan_gap_seconds=maximum_gap,
        scans_with_association=associated_scans,
        association_coverage_percent=100 * associated_scans / scans if scans else None,
        visible_neighbors=visible.response(),
        same_channel_neighbors=same_channel.response(),
        same_ssid_neighbors=same_ssid.response(),
        strong_neighbors=strong.response(),
        strong_neighbor_threshold_dbm=STRONG_NEIGHBOR_THRESHOLD_DBM,
        best_same_ssid_delta_db=delta.response(),
        stronger_same_ssid_scan_count=stronger_scans,
        stronger_same_ssid_percent=100 * stronger_scans / delta.count if delta.count else None,
        association_transition_pairs=association_pairs,
        associated_bssid_changes=bssid_changes,
        associated_frequency_changes=frequency_changes,
        neighborhood_transition_pairs=neighborhood_pairs,
        neighborhood_changed_pairs=neighborhood_changes,
        visible_bss_additions=additions,
        visible_bss_removals=removals,
    )


def get_recording_rf_summary(session: Session, recording_id: str) -> RecordingRfSummary:
    if session.get(DiagnosticRecording, recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    scan, bss = AgentRfScan, AgentRfBssObservation
    query = (
        select(
            scan.id,
            scan.observed_at,
            scan.interface,
            bss.bssid,
            bss.ssid,
            bss.frequency_mhz,
            bss.channel,
            bss.rssi_dbm,
            bss.associated,
        )
        .outerjoin(bss, bss.rf_scan_id == scan.id)
        .where(scan.recording_id == recording_id)
        .order_by(scan.observed_at, scan.id, bss.bssid)
        .execution_options(yield_per=2000)
    )
    return summarize_rf_rows(session.execute(query))
