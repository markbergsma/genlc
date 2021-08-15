# genlm/sam.py

import logging
from typing import Optional, Tuple, Union

from . import const, util
from .gnet import GNetException, GNetMessage, GNetTimeoutException

logger = logging.getLogger(__name__)


class SAMGroup:
    def __init__(self, transport) -> None:
        self.transport = transport
        self.devices: dict = {}

    def set_volume_glm(self, dB: float) -> None:
        """Sets master volume (in dB)"""

        vol_sint24 = util.vol_sint24_from_dB(dB)
        logger.debug(f"volume ({dB} dB): {vol_sint24}\thex: {hex(int(vol_sint24))}")

        msg = GNetMessage(const.GNET_BROADCAST_ADDR, const.CID_VOLUME_GLM)
        msg.set_sint24_data(vol_sint24)
        msg.construct()
        self.transport.send(msg)

    def wakeup_all(self) -> None:
        """
        Monitor wakeup messages

        In practice this is sent twice, with two different data fields for some reason:
        [3, 0x7F], [3, 1]]
        """

        for data in [bytes([3, 0x7F]), bytes([3, 1])]:
            msg = GNetMessage(const.GNET_BROADCAST_ADDR, const.CID_WAKEUP, data=data)
            # Send broadcast message twice
            self.transport.send(msg)
            self.transport.send(msg)

    def shutdown_all(self) -> None:
        """
        Monitor shutdown messages

        In practice this is sent twice, with two different data fields for some reason:
        [3, 2], [3, 0]
        """

        for data in [bytes([3, 2]), bytes([3, 0])]:
            msg = GNetMessage(const.GNET_BROADCAST_ADDR, const.CID_WAKEUP, data=data)
            # Send broadcast message twice
            self.transport.send(msg)
            self.transport.send(msg)

    def race(self) -> int:
        """
        Send a CID_RACE command to discover unassigned monitors on the network
        and await a monitor responding with its 3-byte serial number,
        to be used for address assignment

        Raises a GNetTimeoutException if there are no unassigned SAM monitors left

        Returns:
            The serial (int)
        """

        try:
            resp = self.transport.send_receive(
                GNetMessage(const.GNET_BROADCAST_ADDR, const.CID_RACE)
            ).response
        except GNetTimeoutException:
            raise  # Pass on
        else:
            if len(resp) == 3:
                return int.from_bytes(resp, byteorder="big")
            else:
                raise GNetException(f"Invalid response received to CID_RACE: {resp}")

    def discover_monitors(self, all=False):
        """Generator function to discover SAM monitors and instantiate objects

        if all == True, yield all previously discovered monitors first
        """

        if all:
            yield from self.devices.values()

        first_avail_addr = max(self.devices.keys(), default=1) + 1
        assert first_avail_addr > 1

        for addr in range(first_avail_addr, 128):
            # Broadcast discovery, one by one until there are no unassigned devices left?
            try:
                serialno = self.race()
            except GNetTimeoutException:
                return
            else:
                # Address assignment
                self.assign_address(serialno, addr)
                yield SAMMonitor(addr, serial=serialno, glm=self)

    def assign_address(self, serial: int, address: int) -> None:
        """Assign an address to a SAM monitor after a RACE query"""

        msg = GNetMessage(
            const.GNET_MULTICAST_ADDR,
            const.CID_SET_RID,
            serial.to_bytes(3, byteorder="big") + bytes((address,)),
        )
        resp_msg = self.transport.send_receive(msg)
        if resp_msg.response != bytes((address,)):
            raise GNetException(
                f"Address {address} assignment to monitor with serial {serial} failed,",
                f"response was: {resp_msg.response}",
            )

    def stay_online(self):
        """Broadcasts a STAY_ONLINE message"""

        return self.transport.send(
            GNetMessage(const.GNET_BROADCAST_ADDR, const.CID_STAY_ONLINE)
        )


class BaseDevice:
    """Base class for managing a Gnet/GLM/SAM device"""

    def __init__(self, address: int, group: SAMGroup = None) -> None:
        self.address: int = address
        self.group: SAMGroup = group
        self.poll_fields = {}

        # Add this new instance to the class attribute devices
        if self.group:
            self.group.devices[address] = self

        self.hardware: Tuple[str, str, str, str, str] = ("",) * 5
        self.software_str: str = None
        self.barcode: str = None

        self.logger = logging.getLogger(f"{__name__} {str(self)}")

    def __str__(self) -> str:
        return f"[{self.address}]{self.hardware[0]}#{getattr(self, 'serial', '')}"

    def poll(self) -> dict:
        """Polls the device for status"""
        pass

    def query_software(self) -> str:
        """Queries the device for software information"""

        msg = GNetMessage(self.address, const.CID_SOFTWARE_QUERY2)
        resp_msg = self.group.transport.send_receive(msg)

        self.software_str = resp_msg.response.rstrip(b"\0").rstrip().decode("utf-8")
        return self.software_str

    def query_hardware(self) -> str:
        """Queries the device for hardware information"""

        msg = GNetMessage(self.address, const.CID_HARDWARE_QUERY)
        resp_msg = self.group.transport.send_receive(msg)

        hardware_str = resp_msg.response.rstrip(b"\0").decode("utf-8")
        self.hardware = tuple(hardware_str.rsplit(" ", 5))
        return self.hardware

    def query_barcode(self) -> str:
        """Queries the device for the bar code"""

        msg = GNetMessage(self.address, const.CID_BAR_CODE, b"\x01")
        resp_msg = self.group.transport.send_receive(msg)

        self.barcode = resp_msg.response.decode("utf-8")
        return self.barcode


class USBAdapter(BaseDevice):
    """Class for communicating with the  USB adapter itself"""

    def __init__(self, glm: SAMGroup = None):
        super().__init__(0x01, glm)

    def query_mic_serial(self) -> None:
        msg = GNetMessage(self.address, const.CID_MIC_SERIAL, b"\x82\x44")
        resp_msg = self.group.transport.send_receive(msg)
        self.mic_serial = resp_msg.response.decode("utf-8")
        return self.mic_serial

    def poll(self) -> dict:
        """
        Polls the USB adapter and updates parsed fields in self.poll_fields


        Response bytes:
        0: ?
        1: ? (if no mic is connected, this is the last byte)
        2: ?
        3 - 5: microphone SPL? (linear) - appears to be off by a few dB, possibly calibration, z-weighting
        6: ?
        7: ?
        8: ?
        9 - 11: Some unknown value related to SPL
        12: ?

        GLM also shows (negative) values for "peak" and "RMS"
        """

        msg = GNetMessage(self.address, const.CID_POLL)
        resp = self.group.transport.send_receive(msg).response

        logger.debug(
            f"Poll: {[i for i in resp]}\t{', '.join([hex(i)[2:] for i in resp])}"
        )

        spl_raw = int.from_bytes(resp[3:6], byteorder="big", signed=True)
        fields = {
            "microphone_dBSPL": util.dBSPL_from_sint24(spl_raw) if spl_raw > 0 else 0,
        }
        self.poll_fields.update(fields)
        return fields


class SAMMonitor(BaseDevice):
    """Class for managing a single SAM monitor / subwoofer"""

    def __init__(self, address: int, glm: SAMGroup = None, serial: int = None) -> None:
        self.serial = serial
        super().__init__(address, glm)

    def poll(self) -> dict:
        """
        Polls the device and updates parsed fields in self.poll_fields

        Response bytes:
        0: ?
        1: temperature (C)
        2: ?
        3: ?
        4: ?
        5: ?
        6: input (dBFS)
        7: ?
        8: ?
        9: ?
        10: ?
        11: ?
        12: output (dBFS)
        13: ?
        14: ?
        15: ?
        16: ?
        17: ?
        """

        msg = GNetMessage(self.address, const.CID_POLL)
        resp = self.group.transport.send_receive(msg).response
        if not resp:
            # Empty message
            return

        logger.debug(
            f"Poll: {[i for i in resp]}\t{', '.join([hex(i)[2:] for i in resp])}"
        )

        fields = {
            "temperature": resp[1],
            "input_dBFS": int.from_bytes(resp[6:7], byteorder="big", signed=True),
            "output_dBFS": int.from_bytes(resp[12:13], byteorder="big", signed=True),
        }
        self.poll_fields.update(fields)
        return fields

    def mute(self, mute: bool = True) -> None:
        """Mute the SAM monitor"""

        self.bypass(mute=mute)

    def bypass(
        self,
        value: int = 0,
        mute: Optional[bool] = None,
        led_color: Optional[Union[int, str]] = None,
        led_pulsing: Optional[bool] = None,
        invert_led_enable: Optional[bool] = None,
    ) -> None:
        """Send a BYPASS_QUERY to the monitor

        Arguments:
            value:          Encoded integer value
            mute:           Mute or unmute the sound
            led_color:      LED color
            led_pulsing:    LED pulsing/blinking
        """

        if value is None:
            value = 0
        if mute is not None:
            value |= int(mute)
        if led_color is not None:
            if isinstance(led_color, str) and led_color in [
                "green",
                "red",
                "yellow",
                "off",
            ]:
                led_color = getattr(const, f"LED_{led_color.upper()}")
            assert isinstance(value, int)
            value |= (led_color & 3) << 1
        if led_pulsing is not None:
            value |= int(led_pulsing) << 3
        if invert_led_enable is not None:
            value |= int(invert_led_enable) << 4
        self.logger.debug(f"Encoded bypass value {value} ({bin(value)})")
        data = value.to_bytes(1, byteorder="big")
        self.group.transport.send_receive(
            GNetMessage(self.address, const.CID_BYPASS_QUERY, data)
        )

    def set_digisum_gain(self, gain: int) -> None:
        """Set the digital gain of the SAM monitor"""

        data = gain.to_bytes(2, byteorder="big")
        self.group.transport.send_receive(
            GNetMessage(self.address, const.CID_DIGISUM_GAIN, data)
        )
