import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from wem.api.app import create_app
from wem.profiles.defaults import default_profile_config
from wem.profiles.models import TestProfileConfig as ProfileConfiguration
from wem.profiles.service import ProfileDisabledError, ProfileService
from wem.storage.database import Database
from wem.storage.models import (
    TestProfileRecord as ProfileRecord,
)
from wem.storage.models import (
    TestProfileVersionRecord as ProfileVersionRecord,
)


def test_default_profile_matches_current_hardcoded_behavior() -> None:
    config = default_profile_config()

    assert config.schema_version == 1
    assert config.sampling.wifi_interval_seconds == 5.0
    assert config.tests.gateway.interval_seconds == 5.0
    assert config.tests.gateway.automatic_gateway is True
    assert config.tests.gateway.timeout_seconds == 6.0
    assert config.tests.dns.query == "example.com"
    assert config.tests.internet.target == "1.1.1.1"
    assert config.tests.internet.timeout_seconds == 6.0
    assert config.tests.https.url == "https://example.com"
    assert config.tests.https.timeout_seconds == 5.0
    assert config.application_targets == []
    assert config.thresholds.wifi.rssi_warning_dbm == -75.0
    assert config.thresholds.wifi.rssi_critical_dbm == -82.0
    assert config.thresholds.wifi.retry_warning_percent == 20.0
    assert config.thresholds.wifi.retry_critical_percent == 50.0
    assert config.thresholds.gateway.latency_warning_ms == 50.0
    assert config.thresholds.internet.latency_warning_ms == 150.0
    assert config.thresholds.dns.latency_warning_ms == 250.0
    assert config.thresholds.https.response_warning_ms == 1000.0


@pytest.mark.parametrize(
    "change",
    [
        {"tests": {"https": {"url": "ftp://example.com"}}},
        {
            "thresholds": {
                "wifi": {
                    "rssi_warning_dbm": -75,
                    "rssi_critical_dbm": -70,
                }
            }
        },
        {
            "thresholds": {
                "gateway": {
                    "latency_warning_ms": 50,
                    "packet_loss_warning_percent": 20,
                    "packet_loss_critical_percent": 5,
                }
            }
        },
        {"sampling": {"wifi_interval_seconds": 0}},
        {"tests": {"dns": {"interval_seconds": 7}}},
        {"application_targets": [{"name": "Database", "kind": "tcp", "target": "db.example.com"}]},
        {"unknown": True},
    ],
)
def test_profile_validation_rejects_invalid_configuration(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProfileConfiguration.model_validate(change)


def test_application_targets_are_versioned_and_validate_names_and_cadence() -> None:
    config = ProfileConfiguration.model_validate(
        {
            "application_targets": [
                {
                    "name": "Portal",
                    "kind": "http",
                    "target": "https://portal.example.com/health",
                    "interval_seconds": 10,
                    "timeout_seconds": 3,
                }
            ]
        }
    )
    assert config.application_targets[0].name == "Portal"

    with pytest.raises(ValidationError):
        ProfileConfiguration.model_validate(
            {
                "application_targets": [
                    {"name": "Portal", "kind": "dns", "target": "a.example.com"},
                    {"name": "portal", "kind": "dns", "target": "b.example.com"},
                ]
            }
        )

    with pytest.raises(ValidationError):
        ProfileConfiguration.model_validate(
            {
                "application_targets": [
                    {
                        "name": "Portal",
                        "kind": "dns",
                        "target": "a.example.com",
                        "interval_seconds": 7,
                    }
                ]
            }
        )


def test_database_bootstraps_default_profile_once(tmp_path) -> None:
    database = Database(str(tmp_path / "profiles.db"))
    database.initialize()
    database.initialize()

    service = ProfileService(database)
    profile, version = service.active()

    assert profile.name == "Default"
    assert profile.enabled is True
    assert profile.active_version_id == version.id
    assert version.version == 1
    assert service.configuration(version) == default_profile_config()

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ProfileRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ProfileVersionRecord)) == 1


def test_profile_service_versions_are_immutable_and_activation_is_unique(tmp_path) -> None:
    database = Database(str(tmp_path / "profiles.db"))
    database.initialize()
    service = ProfileService(database)

    custom, first = service.create(
        name="Branch Office",
        description="Higher-latency branch profile",
        enabled=True,
        config=default_profile_config(),
    )
    changed = default_profile_config().model_copy(deep=True)
    changed.tests.dns.query = "internal.example.com"
    custom, second = service.update(
        custom.id,
        name=custom.name,
        description=custom.description,
        enabled=True,
        config=changed,
    )

    assert first.version == 1
    assert second.version == 2
    assert service.configuration(service.version(custom.id, 1)).tests.dns.query == "example.com"
    assert service.configuration(service.version(custom.id, 2)).tests.dns.query == (
        "internal.example.com"
    )

    activated, active_version = service.activate(custom.id)
    assert activated.active_version_id == active_version.id == second.id
    default, _ = service.get(1)
    assert default.active_version_id is None
    assert service.active()[0].id == custom.id

    disabled, _ = service.create(
        name="Disabled",
        description=None,
        enabled=False,
        config=default_profile_config(),
    )
    with pytest.raises(ProfileDisabledError):
        service.activate(disabled.id)


def test_profile_api_crud_versioning_and_activation(tmp_path) -> None:
    database_path = str(tmp_path / "profiles.db")
    with TestClient(create_app(database_path)) as client:
        active = client.get("/profiles/active")
        assert active.status_code == 200
        assert active.json()["name"] == "Default"
        assert active.json()["version"] == 1
        assert active.json()["active"] is True

        created = client.post(
            "/profiles",
            json={
                "name": "  Branch Office  ",
                "description": "Branch profile",
                "configuration": {"tests": {"dns": {"query": "branch.example.com"}}},
            },
        )
        assert created.status_code == 201
        profile_id = created.json()["id"]
        assert created.json()["name"] == "Branch Office"
        assert created.json()["active"] is False
        assert created.json()["configuration"]["tests"]["dns"]["query"] == ("branch.example.com")

        configuration = created.json()["configuration"]
        configuration["tests"]["dns"]["query"] = "updated.example.com"
        updated = client.put(
            f"/profiles/{profile_id}",
            json={"description": None, "configuration": configuration},
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        assert updated.json()["description"] is None

        versions = client.get(f"/profiles/{profile_id}/versions")
        assert versions.status_code == 200
        assert [item["version"] for item in versions.json()] == [2, 1]
        assert versions.json()[0]["configuration"]["tests"]["dns"]["query"] == (
            "updated.example.com"
        )
        assert versions.json()[1]["configuration"]["tests"]["dns"]["query"] == (
            "branch.example.com"
        )

        activated = client.post(f"/profiles/{profile_id}/activate")
        assert activated.status_code == 200
        assert activated.json()["active"] is True
        assert client.get("/profiles/active").json()["id"] == profile_id
        profiles = client.get("/profiles").json()
        assert sum(item["active"] for item in profiles) == 1

        cannot_disable = client.put(f"/profiles/{profile_id}", json={"enabled": False})
        assert cannot_disable.status_code == 409


def test_profile_api_reports_conflicts_and_validation_errors(tmp_path) -> None:
    with TestClient(create_app(str(tmp_path / "profiles.db"))) as client:
        duplicate = client.post("/profiles", json={"name": "Default"})
        assert duplicate.status_code == 409

        invalid_url = client.post(
            "/profiles",
            json={
                "name": "Invalid URL",
                "configuration": {"tests": {"https": {"url": "ftp://example.com"}}},
            },
        )
        assert invalid_url.status_code == 422

        disabled = client.post(
            "/profiles",
            json={"name": "Disabled", "enabled": False},
        )
        assert disabled.status_code == 201
        response = client.post(f"/profiles/{disabled.json()['id']}/activate")
        assert response.status_code == 409

        assert client.get("/profiles/9999").status_code == 404
        assert client.get("/profiles/1/versions/9999").status_code == 404


def test_configuration_is_stored_as_valid_json(tmp_path) -> None:
    database = Database(str(tmp_path / "profiles.db"))
    database.initialize()

    with database.session() as session:
        version = session.scalar(select(ProfileVersionRecord))
        assert version is not None
        assert json.loads(version.config_json)["schema_version"] == 1
