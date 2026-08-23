# genlc/transport.py

"""Generic datagram transport interface for genlc"""

import logging

import hid

from . import const
from .gnet import GNetException, GNetMessage, GNetResponseMessage

logger = logging.getLogger(__name__)


class BaseTransport:
    """Abstract base transport class"""

    def __init__(self):
        pass

    def _write(self, payload: bytes) -> None:
        pass

    def _read(self) -> bytearray:
        pass

    def send(self, message: GNetMessage) -> None:
        self._write(bytes(message))

    def receive(self, parse: bool = True) -> GNetResponseMessage:
        msg = GNetResponseMessage(self._read())
        if parse:
            msg.parse()
        return msg

    def send_receive(self, message: GNetMessage) -> GNetResponseMessage:
        """Combined send-and-receive function"""

        self.send(message)
        return self.receive()


class USBTransport(BaseTransport):
    """Class implementing the USB HID transport compatible with the Genelec GLM adapter"""

    MAX_SEGMENTS = 3
    MAX_PACKET_LEN = 64

    def __init__(self, adapter: hid.Device):
        super().__init__()
        self.adapter: hid.Device = adapter  # FIXME: rename to _adapter

    def _write(self, payload: bytes) -> None:
        """Writes a stream of bytes to the underlying transport hid.Device"""

        logger.debug(f"Sent: {payload}")
        self.adapter.write(payload)

    @staticmethod
    def escape(msg: bytearray) -> bytearray:
        """Perform PPP stuffing."""

        if msg and msg[-1] == const.USB_HID_TERM:
            msg = msg[:-1]

        # The message up to the terminator should be escaped with "PPP stuffing"
        return msg.replace(b"\x7D", b"\x7D\x5D").replace(
            b"\x7E", b"\x7D\x5E"
        ) + bytes([const.USB_HID_TERM])

    @staticmethod
    def unescape(msg: bytearray) -> bytearray:
        """Perform PPP destuffing"""

        return msg.replace(b"\x7D\x5E", b"\x7E").replace(b"\x7D\x5D", b"\x7D")

    def _read(self) -> bytearray:
        """
        Reads one or more packets from the underlying transport hid.Device
        and reassembles them into a single byte string.

        The wire-level terminator is stripped here so that GNetMessage/GNetResponseMessage
        operate on the normalized payload plus CRC.
        """

        segments = []
        while not segments or not segments[-1].rstrip(b"\0").endswith(
            bytes((const.USB_HID_TERM,))
        ):
            if len(segments) + 1 > self.MAX_SEGMENTS:
                raise GNetException(
                    f"Maximum number of response segments ({self.MAX_SEGMENTS}) exceeded."
                )
            segments.append(self.adapter.read(self.MAX_PACKET_LEN))
            # First byte appears to be remaining payload len in this packet (always 63?)
            assert segments[-1][0] == self.MAX_PACKET_LEN - 1, f"value: {segments}"
            assert (
                len(segments[-1]) == self.MAX_PACKET_LEN
            ), f"value: {len(segments[-1]), segments}"

        # Join segments together and strip trailing NULL bytes and wire terminator.
        message = bytearray().join(segment[1:] for segment in segments).rstrip(b"\0")
        logger.debug(f"Rcvd: {bytes(message)}")

        # Perform PPP destuffing and remove the transport-specific terminator.
        message = self.unescape(message)
        if message and message[-1] == const.USB_HID_TERM:
            message = message[:-1]
        return message

    def send(self, message: GNetMessage) -> None:
        """Send a GLMMessage to the GLM adapter"""

        assert message.msg, "Message was not constructed"

        # TODO: split over multiple 64-byte packets when needed

        # Strip any transport-level terminator from the message body, then re-add it
        # as part of the USB HID framing.
        msg = self.escape(bytes(message))

        # Prefix the message with a 0 byte, and 0x80 + len(message)
        payload = bytes((0, 0x80 + len(msg))) + msg
        self._write(payload)

    def receive(self, parse: bool = True) -> GNetResponseMessage:
        """
        Receives a message

        Args:
            parse: Attempt to parse the message using GNetResponseMessage.parse()
            (default: True)

        Returns:
            a GNetResponseMessage
        """

        message = self._read()
        resp = GNetResponseMessage(message)
        if parse:
            resp.parse()
        return resp
