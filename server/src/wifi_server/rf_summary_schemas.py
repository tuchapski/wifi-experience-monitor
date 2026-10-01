"""Descriptive RF evidence; counts refer to BSS observations, never physical APs."""

from datetime import datetime

from pydantic import BaseModel


class RfSampleStatistics(BaseModel):
    sample_count: int
    minimum: float | None
    average: float | None
    maximum: float | None


class RecordingRfSummary(BaseModel):
    scan_count: int
    total_bss_observations: int
    unique_bss: int
    unique_ssids: int
    first_scan_at: datetime | None
    last_scan_at: datetime | None
    maximum_scan_gap_seconds: float | None
    scans_with_association: int
    association_coverage_percent: float | None
    visible_neighbors: RfSampleStatistics
    same_channel_neighbors: RfSampleStatistics
    same_ssid_neighbors: RfSampleStatistics
    strong_neighbors: RfSampleStatistics
    strong_neighbor_threshold_dbm: float
    best_same_ssid_delta_db: RfSampleStatistics
    stronger_same_ssid_scan_count: int
    stronger_same_ssid_percent: float | None
    association_transition_pairs: int
    associated_bssid_changes: int
    associated_frequency_changes: int
    neighborhood_transition_pairs: int
    neighborhood_changed_pairs: int
    visible_bss_additions: int
    visible_bss_removals: int
