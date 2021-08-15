# tests/test_gnet.py


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
    assert bytes(resp.msg)[:-3] == payload

    # FIXME: extend
