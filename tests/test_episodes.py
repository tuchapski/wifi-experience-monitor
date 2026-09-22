import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from wem.analysis.episodes import (
    CorrelationObservation,
    EpisodeIncident,
    ExperienceEpisodeEngine,
)
from wem.api.app import create_app
from wem.models.metrics import IncidentEvent
from wem.storage.database import Database
from wem.storage.incidents import IncidentRepository
from wem.storage.models import SnapshotRecord

START = datetime(2026, 9, 22, 12, tzinfo=UTC)


def incident(
    incident_id: int,
    offset_seconds: int,
    duration_seconds: int | None,
    *,
    code: str,
    domain: str,
    severity: str = "warning",
) -> EpisodeIncident:
    started = START + timedelta(seconds=offset_seconds)
    resolved = (
        started + timedelta(seconds=duration_seconds) if duration_seconds is not None else None
    )
    return EpisodeIncident(
        id=incident_id,
        code=code,
        domain=domain,
        severity=severity,
        message=code,
        started_at=started,
        resolved_at=resolved,
    )


def test_groups_overlapping_and_nearby_incidents_but_splits_later_events() -> None:
    engine = ExperienceEpisodeEngine(merge_gap_seconds=120)
    result = engine.build(
        [
            incident(1, 0, 60, code="WIFI_LOW_SIGNAL", domain="wifi"),
            incident(2, 150, 30, code="GATEWAY_HIGH_LATENCY", domain="gateway"),
            incident(3, 400, 20, code="DNS_HIGH_LATENCY", domain="dns"),
        ],
        now=START + timedelta(seconds=500),
    )

    episodes = result["episodes"]
    assert result["merge_gap_seconds"] == 120
    assert len(episodes) == 2
    assert episodes[1]["episode_id"] == "episode-1"
    assert episodes[1]["incident_count"] == 2
    assert episodes[1]["codes"] == ["WIFI_LOW_SIGNAL", "GATEWAY_HIGH_LATENCY"]
    assert episodes[0]["episode_id"] == "episode-3"


def test_active_incident_keeps_overlapping_episode_open() -> None:
    engine = ExperienceEpisodeEngine()
    result = engine.build(
        [
            incident(1, 0, None, code="SERVICE_SLO_DNS", domain="service_slo"),
            incident(2, 300, 30, code="DNS_FAILURE", domain="dns", severity="critical"),
        ],
        now=START + timedelta(seconds=600),
    )

    episode = result["episodes"][0]
    assert episode["status"] == "active"
    assert episode["ended_at"] is None
    assert episode["severity"] == "critical"
    assert episode["duration_seconds"] == 600.0


def test_correlation_is_assigned_only_when_episode_snapshots_agree() -> None:
    engine = ExperienceEpisodeEngine()
    incidents = [incident(1, 0, 180, code="DNS_FAILURE", domain="dns")]
    correlated = engine.build(
        incidents,
        [
            CorrelationObservation(START + timedelta(seconds=20), "correlated", "dns"),
            CorrelationObservation(START + timedelta(seconds=40), "correlated", "dns"),
        ],
        now=START + timedelta(seconds=300),
    )["episodes"][0]
    assert correlated["correlation_status"] == "correlated"
    assert correlated["primary_domain"] == "dns"
    assert correlated["correlation_domain_counts"] == {"dns": 2}

    mixed = engine.build(
        incidents,
        [
            CorrelationObservation(START + timedelta(seconds=20), "correlated", "dns"),
            CorrelationObservation(START + timedelta(seconds=40), "correlated", "internet"),
        ],
        now=START + timedelta(seconds=300),
    )["episodes"][0]
    assert mixed["correlation_status"] == "mixed"
    assert mixed["primary_domain"] is None


def test_episode_history_endpoint_uses_stored_correlation(tmp_path) -> None:
    database_path = str(tmp_path / "episodes.db")
    database = Database(database_path)
    database.initialize()
    incidents = IncidentRepository(database)

    for code, domain, opened, resolved in (
        ("DNS_FAILURE", "dns", 10, 50),
        ("SERVICE_SLO_DNS", "service_slo", 100, 130),
    ):
        incidents.process_event(
            IncidentEvent(
                action="opened",
                code=code,
                domain=domain,
                severity="warning",
                message=code,
                first_seen_at=(START + timedelta(seconds=opened - 5)).isoformat(),
                opened_at=(START + timedelta(seconds=opened)).isoformat(),
                resolved_at=None,
            )
        )
        incidents.process_event(
            IncidentEvent(
                action="resolved",
                code=code,
                domain=domain,
                severity="warning",
                message=code,
                first_seen_at=(START + timedelta(seconds=opened - 5)).isoformat(),
                opened_at=(START + timedelta(seconds=opened)).isoformat(),
                resolved_at=(START + timedelta(seconds=resolved)).isoformat(),
            )
        )

    with database.session() as session:
        session.add(
            SnapshotRecord(
                timestamp=(START + timedelta(seconds=30)).replace(tzinfo=None),
                interface="wlan0",
                overall_status="warning",
                snapshot_json=json.dumps(
                    {
                        "correlation": {
                            "status": "correlated",
                            "primary_domain": "dns",
                        }
                    }
                ),
            )
        )
        session.commit()

    with TestClient(create_app(database_path)) as client:
        response = client.get("/episodes/history?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["merge_gap_seconds"] == 120
    assert len(body["episodes"]) == 1
    assert body["episodes"][0]["incident_count"] == 2
    assert body["episodes"][0]["primary_domain"] == "dns"
