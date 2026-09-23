import threading
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from wem.collectors.interfaces import WirelessInterface
from wem.profiles.service import ProfileService
from wem.runtime.controller import SensorController
from wem.storage.models import MonitoringSessionRecord


def test_starts_stopped_and_requires_selection(tmp_path):
    with patch("wem.runtime.controller.ConsoleSensorRuntime") as runtime:
        controller = SensorController(str(tmp_path / "test.db"))
        assert controller.status()["running"] is False
        assert controller.status()["started_at"] is None
        with pytest.raises(RuntimeError, match="No wireless interface"):
            controller.start()
        runtime.assert_not_called()


def test_revalidates_interface_at_start(tmp_path):
    controller = SensorController(str(tmp_path / "test.db"))
    controller.configure("wlan0", 5)
    with patch("wem.runtime.controller.WirelessInterfaceDiscovery.discover", return_value=[]):
        with pytest.raises(RuntimeError, match="not an available wireless"):
            controller.start()
    assert not controller.running


def test_restart_creates_fresh_runtime(tmp_path):
    collected = threading.Event()
    runtime = MagicMock()
    runtime.on_snapshot.side_effect = lambda snapshot: collected.set()
    controller = SensorController(str(tmp_path / "test.db"))
    controller.configure("wlan0", 5)
    with (
        patch(
            "wem.runtime.controller.WirelessInterfaceDiscovery.discover",
            return_value=[WirelessInterface(name="wlan0")],
        ),
        patch("wem.runtime.controller.ConsoleSensorRuntime", return_value=runtime) as factory,
    ):
        for _ in range(2):
            collected.clear()
            controller.start()
            try:
                assert collected.wait(2)
                assert controller.status()["started_at"] is not None
            finally:
                controller.stop()
            assert not controller.running
        assert factory.call_count == 2


def test_constructor_failure_is_reported(tmp_path):
    controller = SensorController(str(tmp_path / "test.db"))
    controller.configure("wlan0", 5)
    with (
        patch(
            "wem.runtime.controller.WirelessInterfaceDiscovery.discover",
            return_value=[WirelessInterface(name="wlan0")],
        ),
        patch("wem.runtime.controller.ConsoleSensorRuntime", side_effect=RuntimeError("failed")),
    ):
        controller.start()
        controller._thread.join(timeout=2)
    assert not controller.running
    assert controller.status()["last_error"] == "failed"


def test_running_session_pins_profile_version_and_is_persisted(tmp_path):
    database_path = str(tmp_path / "test.db")
    collected = threading.Event()
    runtime = MagicMock()
    runtime.on_snapshot.side_effect = lambda snapshot: collected.set()
    controller = SensorController(database_path)
    controller.configure("wlan0", 30)

    with (
        patch(
            "wem.runtime.controller.WirelessInterfaceDiscovery.discover",
            return_value=[WirelessInterface(name="wlan0")],
        ),
        patch("wem.runtime.controller.ConsoleSensorRuntime", return_value=runtime) as factory,
    ):
        controller.start()
        assert collected.wait(2)
        started_status = controller.status()
        service = ProfileService(controller.database)
        profile, _ = service.active()
        changed = service.configuration(service.active()[1])
        changed.tests.dns.query = "new.example.com"
        _, new_version = service.update(
            profile.id,
            name=profile.name,
            description=profile.description,
            enabled=True,
            config=changed,
        )

        assert new_version.version == 2
        assert controller.status()["profile_version"] == 1
        runtime_config = factory.call_args.args[0]
        assert runtime_config.profile_config.tests.dns.query == "example.com"
        controller.stop()
        stopped_status = controller.status()
        assert stopped_status["session_id"] is None
        assert stopped_status["profile_version"] == 2

    with controller.database.session() as session:
        record = session.scalar(select(MonitoringSessionRecord))
        assert record is not None
        assert record.id == started_status["session_id"]
        assert record.profile_version_id == started_status["profile_version_id"]
        assert record.status == "stopped"
        assert record.ended_at is not None
