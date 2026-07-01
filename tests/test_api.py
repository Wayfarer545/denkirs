"""Behavioural tests for the Denkirs gateway client."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from custom_components.denkirs.api import (
    DenkirsConnectionError,
    DenkirsGateway,
    LampAddress,
    LampState,
)

LAMP = LampAddress(device_id="dev123", cid="0018")


@pytest.fixture
def tuya_device() -> Iterator[MagicMock]:
    """Patch tinytuya so every Device() returns one shared mock."""
    with patch("custom_components.denkirs.api.tinytuya") as tuya:
        device = MagicMock()
        tuya.Device.return_value = device
        device.status.return_value = {"dps": {"1": False}}
        device.set_multiple_values.return_value = {"dps": {"1": True}}
        device._tuya = tuya  # expose for call-count assertions
        yield device


def _gateway() -> DenkirsGateway:
    return DenkirsGateway("192.168.1.10", "gwid", "localkey")


async def test_poll_parses_full_status(tuya_device: MagicMock) -> None:
    """A complete datapoint payload maps onto a LampState."""
    tuya_device.status.return_value = {
        "dps": {"1": True, "2": "white", "3": 500, "4": 100, "7": 0},
        "cid": "0018",
    }
    state = await _gateway().async_poll(LAMP)
    assert state == LampState(power=True, brightness=500, color_temp=100, mode="white")


async def test_poll_tolerates_missing_datapoints(tuya_device: MagicMock) -> None:
    """A fixture reporting only power yields None for absent datapoints."""
    tuya_device.status.return_value = {"dps": {"1": False}}
    state = await _gateway().async_poll(LAMP)
    assert state == LampState(power=False, brightness=None, color_temp=None, mode=None)


async def test_poll_raises_on_protocol_error(tuya_device: MagicMock) -> None:
    """A Tuya error envelope becomes a connection error."""
    tuya_device.status.return_value = {"Error": "bad key", "Err": "914"}
    with pytest.raises(DenkirsConnectionError):
        await _gateway().async_poll(LAMP)


async def test_poll_raises_when_payload_malformed(tuya_device: MagicMock) -> None:
    """A response without a dps mapping is treated as a failure."""
    tuya_device.status.return_value = None
    with pytest.raises(DenkirsConnectionError):
        await _gateway().async_poll(LAMP)


async def test_apply_power_only_writes_switch(tuya_device: MagicMock) -> None:
    """Applying power alone writes just the boolean switch datapoint."""
    await _gateway().async_apply(LAMP, power=True)
    tuya_device.set_multiple_values.assert_called_once_with({"1": True})


async def test_apply_writes_native_brightness(tuya_device: MagicMock) -> None:
    """Brightness is written on the device's native scale."""
    await _gateway().async_apply(LAMP, brightness=750)
    tuya_device.set_multiple_values.assert_called_once_with({"3": 750})


async def test_apply_writes_native_color_temp(tuya_device: MagicMock) -> None:
    """Colour temperature is written on the device's native scale."""
    await _gateway().async_apply(LAMP, color_temp=250)
    tuya_device.set_multiple_values.assert_called_once_with({"4": 250})


async def test_apply_combines_settings_in_one_write(tuya_device: MagicMock) -> None:
    """Several settings are written together as a single command."""
    await _gateway().async_apply(LAMP, power=True, brightness=500, color_temp=100)
    tuya_device.set_multiple_values.assert_called_once_with(
        {"1": True, "3": 500, "4": 100}
    )


async def test_apply_without_settings_is_a_noop(tuya_device: MagicMock) -> None:
    """Applying nothing touches neither the socket nor the device."""
    await _gateway().async_apply(LAMP)
    tuya_device.set_multiple_values.assert_not_called()


async def test_command_raises_on_protocol_error(tuya_device: MagicMock) -> None:
    """A failed write surfaces as a connection error."""
    tuya_device.set_multiple_values.return_value = {"Err": "905"}
    with pytest.raises(DenkirsConnectionError):
        await _gateway().async_apply(LAMP, power=True)


async def test_sub_device_created_once_per_lamp(tuya_device: MagicMock) -> None:
    """Repeated access reuses the gateway and per-lamp device objects."""
    gateway = _gateway()
    await gateway.async_poll(LAMP)
    await gateway.async_poll(LAMP)
    # One construction for the gateway, one for the lamp, then reused.
    assert tuya_device._tuya.Device.call_count == 2


async def test_disconnect_closes_open_sockets(tuya_device: MagicMock) -> None:
    """Disconnecting closes every device it opened."""
    gateway = _gateway()
    await gateway.async_poll(LAMP)
    await gateway.async_disconnect()
    assert tuya_device.close.called


async def test_poll_raises_when_dps_missing(tuya_device: MagicMock) -> None:
    """A response without a dps mapping is treated as a failure."""
    tuya_device.status.return_value = {"cid": "0018"}
    with pytest.raises(DenkirsConnectionError):
        await _gateway().async_poll(LAMP)


async def test_transport_exception_becomes_connection_error(
    tuya_device: MagicMock,
) -> None:
    """A bare exception from tinytuya is wrapped as a connection error."""
    tuya_device.status.side_effect = OSError("socket closed")
    with pytest.raises(DenkirsConnectionError):
        await _gateway().async_poll(LAMP)


def test_gateway_exposes_its_id() -> None:
    """The gateway id is available for device metadata."""
    assert _gateway().gateway_id == "gwid"
