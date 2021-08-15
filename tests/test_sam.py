# tests/test_sam.py

from contextlib import contextmanager

import pytest
from genlc import const, gnet, sam


@contextmanager
def does_not_raise():
    yield


def test_USBAdapter_init(samgroup):
    """Tests the USBAdapter constructor"""

    ua = sam.USBAdapter(samgroup)
    assert ua.address == 0x01
    assert ua.group is samgroup
    assert ua.address in samgroup.devices
    assert ua.hardware == ("",) * 5
    assert ua.software_str == None
    assert ua.barcode == None
    assert ua.poll_fields == {}


def test_USBAdapter_query_mic_serial(samgroup):
    ua = sam.USBAdapter(samgroup)
    samgroup.transport._read.return_value = b"\x01\t012345\xE8\x00\x7E"
    ua.query_mic_serial()
    samgroup.transport.send.assert_called_once_with(
        gnet.GNetMessage(0x01, 0x51, b"\x82\x44")
    )
    assert ua.mic_serial == "012345"


def test_USBAdapter_query_hardware_software_barcode(samgroup):
    """Test the query functions of USBAdapter"""

    ua = sam.USBAdapter(samgroup)
    samgroup.transport._read.return_value = b"\x01\t1 2 3 4 5\xC6\x90\x7E"
    ua.query_hardware()
    ua.query_software()
    ua.query_barcode()
    assert ua.software_str and isinstance(ua.software_str, str)
    assert ua.barcode and isinstance(ua.barcode, str)
    assert ua.hardware == ("1", "2", "3", "4", "5")


def test_SAMMonitor_init(samgroup):
    """Tests the SAMMonitor constructor"""

    ua = sam.SAMMonitor(0x05, samgroup)
    assert ua.address == 0x05
    assert ua.group is samgroup
    assert samgroup.devices[ua.address] is ua
    assert ua.hardware == ("",) * 5
    assert ua.software_str == None
    assert ua.barcode == None
    assert ua.poll_fields == {}


def test_SAMMonitor_poll(samgroup):
    """Test SAMMonitor.poll with example output"""

    ua = sam.SAMMonitor(0x05, samgroup)
    samgroup.transport._read.return_value = b"\x01\t\x5D\xE7\x7E"
    ua.poll()
    assert "temperature" not in ua.poll_fields
    samgroup.transport._read.return_value = (
        b"\x01\tA\x16\x83\x00\x1eB\x96F\x93C\x80E\x82G\x01\x84\x01e\x9bK~"
    )
    ua.poll()
    assert (
        ua.poll_fields["temperature"] == 22
        and ua.poll_fields["input_dBFS"] == -106
        and ua.poll_fields["output_dBFS"] == -126
    )


def test_SAMGroup_init(mock_transport):
    """Tests the GLM constructor"""

    samgroup = sam.SAMGroup(mock_transport)
    assert samgroup.transport is mock_transport


@pytest.mark.parametrize(
    "vol_dB,raw",
    [(0.0, b"\x7F\xFF\xFF"), (-4.5, b"\x4C\x3E\xA7"), (-20.0, b"\x0C\xCC\xCC")],
)
def test_SAMGroup_set_volume_glm(vol_dB, raw, samgroup):
    """Tests GLM.set_volume_glm with a few input volumes"""
    samgroup.set_volume_glm(vol_dB)
    samgroup.transport.send.assert_called_once()
    assert samgroup.transport.send.call_args.args[0] == gnet.GNetMessage(
        0xFF, 0x1F, raw
    )


def test_SAMGroup_wakeup_all_shutdown_all(samgroup, mocker, caplog):
    """Tests GLM.wakeup_all and GLM.shutdown_all methods"""

    calls = (
        [mocker.call(gnet.GNetMessage(0xFF, 0x3A, b"\x03\x7F"))] * 2
        + [mocker.call(gnet.GNetMessage(0xFF, 0x3A, b"\x03\x01"))] * 2
        + [mocker.call(gnet.GNetMessage(0xFF, 0x3A, b"\x03\x02"))] * 2
        + [mocker.call(gnet.GNetMessage(0xFF, 0x3A, b"\x03\x00"))] * 2
    )
    samgroup.wakeup_all()
    samgroup.shutdown_all()
    assert samgroup.transport.send.call_args_list == calls


def test_SAMGroup_race(samgroup):
    """Tests GLM.race"""

    samgroup.transport._read.return_value = b"\x01\t\x01\x02\x03\xC7\xE8\x7E"
    r = samgroup.race()
    samgroup.transport.send.assert_called_once_with(gnet.GNetMessage(0xFF, 0xFE))
    assert r == 0x010203


@pytest.mark.parametrize(
    "address,serial,response,expectation",
    [
        (2, 123, b"\x02", does_not_raise()),
        (5, 5, b"", pytest.raises(gnet.GNetException)),
    ],
)
def test_SAMGroup_assign_address(
    address, serial, response, expectation, samgroup, mocker
):
    resp = gnet.GNetResponseMessage()
    resp.response = response
    samgroup.transport.send_receive = mocker.Mock(return_value=resp)

    with expectation:
        samgroup.assign_address(serial, address)

    # Verify invocation of send_receive
    samgroup.transport.send_receive.assert_called_once()
    gm = samgroup.transport.send_receive.call_args[0][0]
    assert isinstance(gm, gnet.GNetMessage)
    assert gm.address == const.GNET_MULTICAST_ADDR
    assert gm.command == const.CID_SET_RID
    assert gm.data == serial.to_bytes(3, byteorder="big") + bytes([address])


def test_SAMGroup_discover_monitors(mocker, samgroup):
    """Test the generator method discover_monitors"""

    serials = [0x010203, 0x040506, 0x070809, gnet.GNetTimeoutException("end of race")]

    samgroup.race = mocker.Mock()
    samgroup.race.side_effect = serials
    samgroup.assign_address = mocker.Mock()

    monitors = (monitor for monitor in samgroup.discover_monitors())
    monitors = list(monitors)
    assert len(monitors) == 3
    assert samgroup.assign_address.call_args_list == [
        mocker.call(*args) for args in zip(serials, range(2, 5))
    ]
    assert all(isinstance(monitor, sam.SAMMonitor) for monitor in monitors)
