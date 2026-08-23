# genlc/transport.py

"""Generic datagram transport interface for genlc"""

import logging

import hid
import serial

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

        # The message should be escaped with "PPP stuffing" before the HID
        # terminator is appended.
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


class RS485Transport(BaseTransport):
    """
    Class implementing a direct RS485 transport to the Gnet bus, bypassing the
    Genelec GLM USB adapter.

    This talks either to a local serial port connected to an RS485 transceiver, or
    to a TCP proxy (such as a Waveshare RS485-to-Ethernet adapter) bridging the bus
    over the network. Any URL supported by pyserial's `serial_for_url()` may be used,
    e.g. "/dev/ttyUSB0" for a local serial port, or "socket://host:port" for a TCP
    proxy.

    Unlike the USB HID transport, the raw RS485 bus does not use packet
    prefixing/segmentation. Framing is currently terminated by "\\x3E", but the
    real on-wire byte-stuffing mechanism is still unknown.

    FIXME: re-sniff the RS485 wire protocol and replace this guessed framing with
    the actual Genelec bus framing rules.
    """

    def __init__(self, url: str, timeout: float = 1.0, **kwargs) -> None:
        super().__init__()
        self._serial: serial.SerialBase = serial.serial_for_url(
            url,
            baudrate=const.RS485_BAUDRATE,
            bytesize=const.RS485_BYTESIZE,
            parity=const.RS485_PARITY,
            stopbits=const.RS485_STOPBITS,
            timeout=timeout,
            **kwargs,
        )

    def close(self) -> None:
        """Closes the underlying serial connection"""

        self._serial.close()

    def _write(self, payload: bytes) -> None:
        """Writes a stream of bytes to the underlying serial connection"""

        logger.debug(f"Sent: {payload}")
        self._serial.write(payload)

    def _read(self) -> bytearray:
        """
        Reads a single frame from the RS485 bus, up to and including the
        transport-specific terminator byte and strips it before returning.
        """

        message = self._serial.read_until(bytes((const.RS485_TERM,)))
        if not message or message[-1] != const.RS485_TERM:
            raise GNetException("Timeout waiting for RS485 terminator byte")

        logger.debug(f"Rcvd: {bytes(message)}")
        return bytearray(message[:-1])

    def send(self, message: GNetMessage) -> None:
        """Send a GNetMessage over the RS485 bus"""

        assert message.msg, "Message was not constructed"

        payload = bytes(message) + bytes((const.RS485_TERM,))
        self._write(payload)

    def receive(self, parse: bool = True) -> GNetResponseMessage:
        """
        Receives a message from the RS485 bus.

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
