from unittest.mock import patch

from wem.main import main


def test_main_serves_api_without_starting_collector(tmp_path):
    with (
        patch("sys.argv", ["wem", "--database", str(tmp_path / "test.db")]),
        patch("wem.main.uvicorn.run") as serve,
        patch("wem.runtime.controller.ConsoleSensorRuntime") as runtime,
    ):
        main()
        serve.assert_called_once()
        runtime.assert_not_called()
