# tests/test_gnet.py

import pytest

from genlc import const, gnet, transport


def test_usbtransport_receive(usb_transport):
    """Tests USBTransport.receive"""

    # Send two packets
    payload = bytes(range(63))
    segments = [
        (b"\x3F" + payload).ljust(64, b"\0"),
        b"\x3F\x00\x00\x7E".ljust(64, b"\0"),
    ]
    usb_transport.adapter.read.side_effect = segments
    resp = usb_transport.receive(parse=False)
    assert bytes(resp.msg).rstrip(b"\0") == payload

    # FIXME: extend


def test_usbtransport_escape_keeps_payload_terminator():
    """Tests USBTransport.escape preserves a trailing payload terminator byte"""

    payload = bytearray(b"\x02\x08\x18\x95\x7E")
    escaped = transport.USBTransport.escape(payload)

    assert escaped == b"\x02\x08\x18\x95\x7D\x5E\x7E"


def test_rs485transport_init(mocker):
    """Tests RS485Transport constructor sets up the serial connection"""

    mock_serial_for_url = mocker.patch("serial.serial_for_url")
    transport.RS485Transport("socket://127.0.0.1:8899")

    mock_serial_for_url.assert_called_once_with(
        "socket://127.0.0.1:8899",
        baudrate=const.RS485_BAUDRATE,
        bytesize=const.RS485_BYTESIZE,
        parity=const.RS485_PARITY,
        stopbits=const.RS485_STOPBITS,
        timeout=1.0,
    )


def test_rs485transport_send(mocker):
    """Tests RS485Transport.send translates terminator and RACE command"""

    mocker.patch("serial.serial_for_url")
    rs485_transport = transport.RS485Transport("socket://127.0.0.1:8899")

    message = gnet.GNetMessage(0x02, 0x08)
    rs485_transport.send(message)
    sent = rs485_transport._serial.write.call_args[0][0]
    assert sent[-1] == const.RS485_TERM
    assert sent == bytes(message) + bytes((const.RS485_TERM,))


def test_rs485transport_send_race(mocker):
    """Tests RS485Transport.send emits CID_RACE as a normal frame"""

    mocker.patch("serial.serial_for_url")
    rs485_transport = transport.RS485Transport("socket://127.0.0.1:8899")

    message = gnet.GNetMessage(const.GNET_BROADCAST_ADDR, const.CID_RACE)
    rs485_transport.send(message)
    sent = rs485_transport._serial.write.call_args[0][0]

    assert sent[-1] == const.RS485_TERM
    assert sent == bytes(message) + bytes((const.RS485_TERM,))


def test_rs485transport_read(mocker):
    """Tests RS485Transport._read reads until the RS485 terminator byte"""

    mocker.patch("serial.serial_for_url")
    rs485_transport = transport.RS485Transport("socket://127.0.0.1:8899")

    payload = b"\x02\x09\x18\x95\x3E"
    rs485_transport._serial.read_until.return_value = payload
    message = rs485_transport._read()

    rs485_transport._serial.read_until.assert_called_once_with(
        bytes((const.RS485_TERM,))
    )
    assert bytes(message) == payload[:-1]


def test_rs485transport_read_timeout(mocker):
    """Tests RS485Transport._read raises on a read timeout (no terminator byte)"""

    mocker.patch("serial.serial_for_url")
    rs485_transport = transport.RS485Transport("socket://127.0.0.1:8899")

    rs485_transport._serial.read_until.return_value = b""
    with pytest.raises(gnet.GNetException):
        rs485_transport._read()


def test_rs485transport_receive(mocker):
    """Tests RS485Transport.receive strips the RS485 wire terminator"""

    mocker.patch("serial.serial_for_url")
    rs485_transport = transport.RS485Transport("socket://127.0.0.1:8899")

    payload = bytes(range(59))
    checksum = b"\x61\xCB"
    rs485_transport._serial.read_until.return_value = (
        b"\x01\x09" + payload + checksum + bytes((const.RS485_TERM,))
    )
    resp = rs485_transport.receive()
    assert resp.response_code == const.GNET_ACK
    assert resp.response == payload


def test_rs485transport_close(mocker):
    """Tests RS485Transport.close closes the underlying serial connection"""

    mocker.patch("serial.serial_for_url")
    rs485_transport = transport.RS485Transport("socket://127.0.0.1:8899")
    rs485_transport.close()
    rs485_transport._serial.close.assert_called_once()
