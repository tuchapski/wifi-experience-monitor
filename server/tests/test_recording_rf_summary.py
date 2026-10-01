from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from wifi_server.api.recordings import router
from wifi_server.db.models import DiagnosticRecording
from wifi_server.dependencies import get_session
from wifi_server.services.rf_summaries import get_recording_rf_summary, summarize_rf_rows

START = datetime(2026, 9, 29, 20, tzinfo=UTC)


def row(scan, bssid, ssid="CORP", frequency=5180, rssi=-65, associated=False, interface="wlan0"):
    return (
        scan,
        START + timedelta(seconds=scan * 60),
        interface,
        bssid,
        ssid,
        frequency,
        1,  # Deliberately collide channel numbers across different bands.
        rssi,
        associated,
    )


def test_density_and_alternative_signal_use_valid_scan_denominators():
    result = summarize_rf_rows(
        [
            row(1, "aa", associated=True, rssi=-70),
            row(1, "bb", rssi=-60),
            row(1, "cc", ssid="GUEST", frequency=2412, rssi=-80),
            row(2, "bb", associated=True, rssi=-60),
            row(2, "aa", rssi=-65),
        ]
    )
    assert result.scan_count == 2
    assert result.unique_bss == 3
    assert result.unique_ssids == 2
    assert result.visible_neighbors.average == 1.5
    assert result.same_channel_neighbors.average == 1  # Frequency, not channel number.
    assert result.same_ssid_neighbors.average == 1
    assert result.strong_neighbors.average == 1
    assert result.best_same_ssid_delta_db.minimum == -5
    assert result.best_same_ssid_delta_db.maximum == 10
    assert result.stronger_same_ssid_scan_count == 1
    assert result.stronger_same_ssid_percent == 50
    assert result.associated_bssid_changes == 1
    assert result.neighborhood_changed_pairs == 1
    assert result.visible_bss_removals == 1
    assert result.maximum_scan_gap_seconds == 60


def test_missing_association_breaks_transition_continuity_and_keeps_comparisons_unknown():
    result = summarize_rf_rows(
        [row(1, "aa", associated=True), row(2, "cc"), row(3, "bb", associated=True)]
    )
    assert result.associated_bssid_changes == 0
    assert result.association_transition_pairs == 0
    assert result.scans_with_association == 2
    assert result.same_channel_neighbors.sample_count == 2
    assert result.same_channel_neighbors.average == 0
    assert result.best_same_ssid_delta_db.sample_count == 0
    assert result.stronger_same_ssid_percent is None

    unknown = summarize_rf_rows([row(1, "aa")])
    assert unknown.same_channel_neighbors.average is None
    assert unknown.same_ssid_neighbors.average is None
    assert unknown.association_coverage_percent == 0


def test_empty_scans_hidden_ssids_and_missing_rssi_are_distinct():
    result = summarize_rf_rows(
        [
            row(1, None, ssid=None, frequency=None, rssi=None),
            row(2, "aa", ssid="", associated=True, rssi=None),
            row(2, "bb", ssid="", rssi=None),
        ]
    )
    assert result.scan_count == 2
    assert result.visible_neighbors.minimum == 0
    assert result.unique_ssids == 0
    assert result.same_ssid_neighbors.sample_count == 0
    assert result.strong_neighbors.sample_count == 1  # Empty scan certifies zero.
    assert result.strong_neighbors.average == 0
    assert result.best_same_ssid_delta_db.average is None


def test_ambiguous_association_and_interface_change_do_not_invent_transitions():
    result = summarize_rf_rows(
        [
            row(1, "aa", associated=True),
            row(2, "aa", associated=True),
            row(2, "bb", associated=True),
            row(3, "cc", associated=True),
            row(4, "dd", associated=True, interface="wlan1"),
        ]
    )
    assert result.scans_with_association == 3
    assert result.association_transition_pairs == 0
    assert result.associated_bssid_changes == 0
    assert result.neighborhood_transition_pairs == 2


def test_frequency_changes_and_case_normalization():
    result = summarize_rf_rows(
        [
            row(1, "AA", associated=True),
            row(2, "aa", frequency=2412, associated=True),
            row(3, "aa", frequency=2412, associated=True),
        ]
    )
    assert result.unique_bss == 1
    assert result.associated_bssid_changes == 0
    assert result.associated_frequency_changes == 1
    assert result.neighborhood_changed_pairs == 0
    assert result.association_transition_pairs == 2


def test_summary_does_not_truncate_early_peaks_in_long_recording():
    def rows():
        for scan in range(2501):
            yield row(scan, "aa", associated=True)
            if scan == 0:
                for neighbor in range(40):
                    yield row(scan, f"neighbor-{neighbor}", rssi=-50)

    result = summarize_rf_rows(rows())
    assert result.scan_count == 2501
    assert result.visible_neighbors.maximum == 40
    assert result.unique_bss == 41
    assert result.stronger_same_ssid_scan_count == 1
    assert result.first_scan_at == START


def test_no_evidence_returns_null_statistics():
    result = summarize_rf_rows([])
    assert result.scan_count == 0
    assert result.visible_neighbors.average is None
    assert result.association_coverage_percent is None
    assert result.first_scan_at is None
    assert result.maximum_scan_gap_seconds is None


def test_query_is_recording_scoped_ordered_and_preserves_empty_scans():
    # Use real SQL execution with only the columns consumed by the summary query.
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE agent_rf_scans (id INTEGER, observed_at DATETIME, "
            "interface TEXT, recording_id TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE agent_rf_bss_observations (rf_scan_id INTEGER, bssid TEXT, "
            "ssid TEXT, frequency_mhz INTEGER, channel INTEGER, rssi_dbm FLOAT, associated BOOLEAN)"
        )
        connection.exec_driver_sql(
            "INSERT INTO agent_rf_scans VALUES "
            "(2, '2026-09-29 20:02:00', 'wlan0', 'rec_test'), "
            "(1, '2026-09-29 20:01:00', 'wlan0', 'rec_test'), "
            "(3, '2026-09-29 20:03:00', 'wlan0', 'rec_other')"
        )
        connection.exec_driver_sql(
            "INSERT INTO agent_rf_bss_observations VALUES "
            "(1, 'aa', 'CORP', 5180, 36, -60, 1), "
            "(3, 'bb', 'OTHER', 2412, 1, -50, 1)"
        )
        session = Mock(spec=Session)
        session.get.return_value = DiagnosticRecording(id="rec_test")
        session.execute.side_effect = connection.execute
        result = get_recording_rf_summary(session, "rec_test")
    assert result.scan_count == 2
    assert result.total_bss_observations == 1
    assert result.unique_bss == 1
    assert result.association_coverage_percent == 50
    assert result.first_scan_at < result.last_scan_at
    query = session.execute.call_args.args[0]
    assert query.get_execution_options()["yield_per"] == 2000


def test_unknown_recording_returns_404():
    session = Mock(spec=Session)
    session.get.return_value = None
    with pytest.raises(HTTPException) as error:
        get_recording_rf_summary(session, "missing")
    assert error.value.status_code == 404
    session.execute.assert_not_called()


def test_summary_endpoint_serializes_evidence_and_propagates_404():
    session = Mock(spec=Session)
    session.get.return_value = DiagnosticRecording(id="rec_test")
    session.execute.return_value = [row(1, "aa", associated=True)]
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get("/api/v1/recordings/rec_test/rf/summary")
        assert response.status_code == 200
        assert response.json()["scan_count"] == 1
        assert response.json()["stronger_same_ssid_percent"] is None
        session.get.return_value = None
        assert client.get("/api/v1/recordings/missing/rf/summary").status_code == 404
