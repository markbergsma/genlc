# tests/test_e2e.py

"""
End-to-end testing with the GLM adapter
"""

import time

import hid
import pytest
from genlc import const, sam, transport


@pytest.mark.e2e
def test_e2e_usb_adapter_poll_all_devices():
    hid_glm_adapter = hid.Device(const.GENELEC_GLM_VID, const.GENELEC_GLM_PID)
    usbtransport = transport.USBTransport(hid_glm_adapter)
    sg = sam.SAMGroup(usbtransport)
    print(
        "Found Genelec GLM adapter:",
        hid_glm_adapter.manufacturer,
        hid_glm_adapter.product,
        "with serial",
        hid_glm_adapter.serial,
    )

    usb_adapter = sam.USBAdapter(sg)
    usb_adapter.query_hardware()
    usb_adapter.query_software()
    usb_adapter.query_barcode()
    print(" ".join(usb_adapter.hardware), usb_adapter.software_str, usb_adapter.barcode)
    print("Microphone serial number", usb_adapter.query_mic_serial())

    # Wakeup all monitors
    sg.wakeup_all()

    # Poll the adapter 5 times (GLM seems to do this on startup)
    for i in range(5):
        usb_adapter.poll()

    for monitor in sg.discover_monitors():
        monitor.query_hardware()
        monitor.query_software()
        monitor.query_barcode()

        print(
            f"[{monitor.address}] Discovered SAM device {monitor.hardware[0]}",
            f"with software version {monitor.software_str.split(';')[2]}",
            f"{monitor.software_str.split(';')[4]}",
            f"serial {monitor.barcode}",
        )
    assert len(sg.devices) > 0

    sg.set_volume_glm(-50.0)

    # Poll the monitors
    for i in range(10):
        for monitor in sg.devices.values():
            d = monitor.poll()
            print(d)

        time.sleep(1)
