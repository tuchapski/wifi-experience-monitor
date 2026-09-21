import threading
from unittest.mock import MagicMock, patch

import pytest

from wem.collectors.interfaces import WirelessInterface
from wem.runtime.controller import SensorController


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
