# tests/test_cli.py

"""
Test the CLI commands of genlc
"""

import genlc.cli
import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_samgroup(mocker):
    r = mocker.patch("genlc.cli.get_samgroup")
    return r.return_value  # Return the mock GLM object


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("0%", "-120.0"),
        ("50%", "-6.020599913279624"),
        ("100%", "0.0"),
        ("-50dB", "-50.0"),
        ("0.0 dB", "0.0"),
    ],
)
def test_set_volume(test_input, expected, runner, mock_samgroup):
    result = runner.invoke(
        genlc.cli.main, ["set-volume", f"--volume={test_input}"], catch_exceptions=False
    )
    mock_samgroup.set_volume_glm.assert_called_with(float(expected))
    assert result.exit_code == 0


def test_wakeup_shutdown(runner, mock_samgroup):
    result = runner.invoke(
        genlc.cli.main, ["wakeup", "shutdown"], catch_exceptions=False
    )
    assert result.exit_code == 0
    mock_samgroup.wakeup_all.assert_called_once()
    mock_samgroup.shutdown_all.assert_called_once()
