# tests/conftest.py

import pytest

from genlc import sam, transport


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end test")


@pytest.fixture
def mock_hid_device(mocker):
    # Mock up an empty class with just enough functionality
    # to mimic hid.Device for our needs
    hid_device = mocker.Mock()
    hid_device.manufacturer = "Genelec"
    hid_device.product = "Gnet Adapter"
    hid_device.serial = "0000000001"
    return hid_device


@pytest.fixture
def mock_transport(mocker):
    mocktr = transport.BaseTransport()
    mocktr._read = mocker.Mock()
    mocktr.send = mocker.Mock()
    return mocktr


@pytest.fixture
def usb_transport(mock_hid_device):
    return transport.USBTransport(mock_hid_device)


@pytest.fixture
def samgroup(mock_transport):
    return sam.SAMGroup(mock_transport)
