# tests/test_cli.py

"""
Test the CLI commands of genlc
"""

import genlc.cli
import pytest
from click.testing import CliRunner
from genlc import const, sam


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_samgroup(mocker):
    r = mocker.patch("genlc.cli.get_samgroup")
    return r.return_value  # Return the mock GLM object


@pytest.fixture
def mock_monitor(mocker, mock_samgroup):
    """Test fixture which returns a single (wrapped) SAMMonitor instance
    (address: 2)
    """

    monitor = mocker.Mock(wraps=sam.SAMMonitor(2, mock_samgroup, 666))
    monitor.address = 2
    return monitor


def test_monitors_option(runner, mocker, mock_samgroup):
    """Test monitors option on the group and (sub) commands"""

    mocker.patch("genlc.cli.validated_monitors")

    result = runner.invoke(
        genlc.cli.main, ["--monitors=2,#12345678", "poll"], catch_exceptions=False
    )
    # Poll should have been passed the --monitors value from the group command
    genlc.cli.validated_monitors.assert_called_with(
        {2, "#12345678"}, allow_address_1=True
    )
    assert result.exit_code == 0

    result = runner.invoke(
        genlc.cli.main,
        ["--monitors=2,#12345678", "poll", "--monitors=4"],
        catch_exceptions=False,
    )
    # Poll should have its own --monitors value passed
    genlc.cli.validated_monitors.assert_called_with({4}, allow_address_1=True)
    assert result.exit_code == 0


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


@pytest.mark.parametrize("xo_freq", [const.DEFAULT_XO_FREQ, 100, 120])
def test_bass_manage(xo_freq, runner, mocker, mock_monitor):
    mocker.patch("genlc.cli.validated_monitors", return_value=[mock_monitor])
    result = runner.invoke(
        genlc.cli.main,
        ["bass-manage", f"--monitors={mock_monitor.address}", f"--xo-freq={xo_freq}"],
        catch_exceptions=False,
    )
    mock_monitor.bass_manage_xo.assert_called_with(xo_freq)
    assert result.exit_code == 0


def test_wakeup_shutdown(runner, mock_samgroup):
    result = runner.invoke(
        genlc.cli.main, ["wakeup", "shutdown"], catch_exceptions=False
    )
    assert result.exit_code == 0
    mock_samgroup.wakeup_all.assert_called_once()
    mock_samgroup.shutdown_all.assert_called_once()
