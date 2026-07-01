"""Tests for Denkirs diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denkirs.api import LampState
from custom_components.denkirs.const import (
    CONF_CID,
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LAMPS,
    CONF_LOCAL_KEY,
    DOMAIN,
)
from custom_components.denkirs.diagnostics import (
    async_get_config_entry_diagnostics,
)

ENTRY_DATA = {
    CONF_HOST: "192.168.1.10",
    CONF_GATEWAY_ID: "gwid",
    CONF_LOCAL_KEY: "supersecret",
    CONF_LAMPS: [
        {
            CONF_DEVICE_ID: "dev-1",
            CONF_CID: "0018",
            CONF_NAME: "Kitchen",
        }
    ],
}
STATE = LampState(power=True, brightness=500, color_temp=100, mode="white")


async def test_diagnostics_redacts_local_key(hass: HomeAssistant) -> None:
    """The local key is redacted while fixture state is reported."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch("custom_components.denkirs.DenkirsGateway") as gateway_cls:
        gateway = gateway_cls.return_value
        gateway.gateway_id = "gwid"
        gateway.async_poll = AsyncMock(return_value=STATE)
        gateway.async_disconnect = AsyncMock()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"][CONF_LOCAL_KEY] == "**REDACTED**"
    assert diagnostics["entry"]["data"][CONF_HOST] == "192.168.1.10"
    assert diagnostics["fixtures"]["0018"]["brightness"] == 500
