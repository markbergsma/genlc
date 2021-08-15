# genlc/gnet.py

import logging
from typing import Optional

import libscrc

from . import const

logger = logging.getLogger(__name__)


class GNetException(Exception):
    """Standard Gnet exception class"""

    pass


class GNetNackException(GNetException):
    """Exception denoting an error response message"""

    pass


class GNetTimeoutException(GNetException):
    """Exception indicating a Gnet timeout (e.g. after CID_RACE)"""

    pass


class GNetMessage:
    """Class for constructing a Gnet message

    Gnet is RS-485 based, and the GLM adapter bridges between RS485 and USB HID
    with little processing.

    Packet format appears to be as follows:
    +---------------+---------------+---------------+---------------+---------------+---------------+
    |   00 ... 07   |   08 ... 15   |  16 ... N-1   |   N ... N+7   | N+8 ... N+15  | N+16 ... N+23 |
    +---------------+---------------+---------------+---------------+---------------+---------------+
    | address (RID) | command (CID) |     data      |     checksum (CRC16/GSM)      |  terminator   |
    |               |               |  (optional)   |     of payload (=)            |     (0x7E)    |
    +===============+===============+===============+---------------+---------------+---------------+

    Fields:

    - address
        Target address of the device the query is directed to.
        0x01        GLM adapter
        0x02...     SAM monitors (after assignment)
        0xF0        Gnet multicast address (all monitors, before assignment)
        0xFF        Gnet broadcast address (all devices)

    - command (CID)
        Command/query code - see const.py

    - data
        Optional, variable length field with data bytes, depending on CID

    - checksum
        CRC16/GSM checksum of the message, starting with the address byte, up to
        and including the data bytes

    - terminator
        Terminator byte, always 0x7E
    """

    def __init__(
        self,
        address: int = None,
        command: int = None,
        data: bytes = bytes(),
    ) -> None:
        self.address: Optional[int] = address
        self.command: Optional[int] = command
        self.data: bytes = data
        self.checksum: Optional[int] = None
        self.msg: Optional[bytearray] = None

        if address and command:
            # If we have a complete packet, make it ready to send rightaway
            self.construct()

    def __repr__(self) -> str:
        return (
            f"GNetMessage({hex(self.address)}, {hex(self.command)}, {repr(self.data)}"
        )

    def __bytes__(self) -> bytes:
        assert self.msg, "Message was not constructed yet"
        return bytes(self.msg)

    def __len__(self) -> int:
        assert self.msg, "Message was not constructed yet"
        return len(self.msg)

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, GNetMessage)
            and self.address == other.address
            and self.command == other.command
            and self.data == other.data
        )

    def construct(self) -> None:
        """Constructs the packet into bytearray msg from the individual field variables"""

        self.msg = bytearray((self.address, self.command)) + self.data
        self.create_checksum()
        self.msg += self.checksum.to_bytes(2, byteorder="big")

        self.msg += bytes([const.GNET_TERM])

    def create_checksum(self) -> int:
        """
        Calculate CRC16/GSM checksum of the address, command & data bytes
        """

        assert len(self.msg) >= 2
        self.checksum = libscrc.gsm16(self.msg)
        return self.checksum

    def set_sint24_data(self, sint24: int) -> None:
        """Set data field from a 24 bit signed integer."""
        self.data = sint24.to_bytes(3, byteorder="big", signed=True)


class GNetResponseMessage:
    """
    Class for holding and parsing a Gnet response message

    Responses appear to have the format:
    <packet length; 63> <response code?> <message>
    """

    def __init__(self, msg: bytearray = None) -> None:
        self.msg: Optional[bytearray] = msg
        self.response_code: Optional[int] = None
        self.response: Optional[bytearray] = None

    def parse(self) -> None:
        """Parses the response message in self.msg"""

        assert self.msg

        # Store the response code (?)
        self.response_code = self.msg[1]
        if self.response_code == const.GNET_TIMEOUT:
            raise GNetTimeoutException()
        elif self.response_code != const.GNET_ACK:
            raise GNetException(f"Response code {self.response_code}")

        if self.msg[-1] != const.GNET_TERM:
            raise GNetException(f"Response message does not end with terminator byte")

        # Extract the checksum and verify it
        checksum = int.from_bytes(self.msg[-3:-1], byteorder="big")
        calculated_checksum = libscrc.gsm16(self.msg[:-3])
        if calculated_checksum != checksum:
            raise GNetException(
                f"Response checksum ({hex(checksum)}) does not match "
                f"message payload {bytes(self.msg[:-3])!r} [{hex(calculated_checksum)}]"
            )

        self.response = bytes(self.msg[2:-3])
