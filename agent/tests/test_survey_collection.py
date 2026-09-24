from unittest.mock import patch

from wifi_agent.collectors.command import CommandResult
from wifi_agent.collectors.wifi import WifiStateCollector


@patch("wifi_agent.collectors.wifi.run_command")
def test_wifi_collector_keeps_survey_counters_when_noise_is_unavailable(
    mock_run_command,
) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout
        if command[-1] == "info":
            return CommandResult(
                "Interface wlp0s20f3\n"
                "    ssid CORP\n"
                "    channel 44 (5220 MHz), width: 80 MHz, center1: 5210 MHz\n",
                "",
                0,
            )
        if command[-1] == "link":
            return CommandResult(
                "Connected to aa:bb:cc:dd:ee:ff (on wlp0s20f3)\n"
                "    SSID: CORP\n"
                "    freq: 5220\n"
                "    signal: -54 dBm\n",
                "",
                0,
            )
        if command[-2:] == ["station", "dump"]:
            return CommandResult("", "", 0)
        if command[-2:] == ["survey", "dump"]:
            return CommandResult(
                "Survey data from wlp0s20f3\n"
                "    frequency: 5220 MHz [in use]\n"
                "    channel active time: 10000 ms\n"
                "    channel busy time: 4200 ms\n"
                "    channel receive time: 2500 ms\n"
                "    channel transmit time: 800 ms\n",
                "",
                0,
            )
        return CommandResult("", "unexpected", 1)

    mock_run_command.side_effect = side_effect
    values = {
        observation.metric: observation.value
        for observation in WifiStateCollector("wlp0s20f3").collect()
    }

    assert values["wifi.survey_active_ms"] == 10000
    assert values["wifi.survey_busy_ms"] == 4200
    assert values["wifi.survey_rx_ms"] == 2500
    assert values["wifi.survey_tx_ms"] == 800
    assert "wifi.noise_dbm" not in values
    assert "wifi.snr_db" not in values
