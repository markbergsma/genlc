# tests/test_gnet.py

import libscrc
import pytest
from genlc import const, gnet


def test_GNetMessage_init():
    """Tests the GNetMessage constructor"""

    gnet_message = gnet.GNetMessage()
    assert gnet_message.msg is None

    gnet_message = gnet.GNetMessage(0x02)
    assert gnet_message.address == 0x02
    assert gnet_message.msg is None

    gnet_message = gnet.GNetMessage(0x02, 0x08)
    assert gnet_message.msg == b"\x02\x08\x18\x95\x7E"


def test_GNetMessage_construct():
    """Tests GNetMessage.construct"""

    gnet_message = gnet.GNetMessage(0x02, 0x08)
    assert gnet_message.checksum == libscrc.gsm16(b"\x02\x08")
    assert gnet_message.msg == b"\x02\x08\x18\x95\x7E"

    gnet_message = gnet.GNetMessage(0xFF, 0x04, b"ab")
    assert gnet_message.checksum == libscrc.gsm16(b"\xFF\x04ab")
    assert gnet_message.msg == b"\xFF\x04ab\x1Cc\x7E"


def test_GNetResponseMessage_parse():
    """Tests GNetResponseMessage.parse"""

    gnrm = gnet.GNetResponseMessage()
    payload = bytes(range(59))
    gnrm.msg = bytearray(b"\x01\x09" + payload + b"\x00\x00\x7E")
    with pytest.raises(gnet.GNetException):
        gnrm.parse()

    # Now let's put a correct CRC for bytes(range(64)) and try again
    gnrm.msg[-3:-1] = b"\x61\xCB"
    gnrm.parse()
    assert gnrm.response_code == const.GNET_ACK
    assert payload == gnrm.response

    # Verify whether a timeout throws an exception
    gnrm.msg[1] = const.GNET_TIMEOUT
    with pytest.raises(gnet.GNetTimeoutException):
        gnrm.parse()
