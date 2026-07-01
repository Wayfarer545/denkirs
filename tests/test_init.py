"""Integration setup and teardown tests for Denkirs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denkirs.api import LampState
from custom_components.denkirs.const import (
    CONF_CID,
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LAMPS,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    DOMAIN,
)

ENTRY_DATA = {
    CONF_HOST: "192.168.1.10",
    CONF_GATEWAY_ID: "gwid",
    CONF_LOCAL_KEY: "localkey",
    CONF_LAMPS: [
        {
            CONF_DEVICE_ID: "dev-1",
            CONF_CID: "0018",
            CONF_NAME: "Kitchen",
            CONF_MODEL: "DK/EU-8003-BK",
        }
    ],
}
STATE = LampState(power=True, brightness=500, color_temp=100, mode="white")


def _mock_gateway(gateway_cls: object) -> AsyncMock:
    gateway = gateway_cls.return_value
    gateway.gateway_id = "gwid"
    gateway.async_poll = AsyncMock(return_value=STATE)
    gateway.async_disconnect = AsyncMock()
    return gateway


async def test_setup_creates_entities_and_unload_disconnects(
    hass: HomeAssistant,
) -> None:
    """A configured entry loads a light entity and unloading closes the socket."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch("custom_components.denkirs.DenkirsGateway") as gateway_cls:
        gateway = _mock_gateway(gateway_cls)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert hass.states.get("light.kitchen") is not None

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    gateway.async_disconnect.assert_awaited_once()


async def test_options_change_reloads_entry(hass: HomeAssistant) -> None:
    """Updating options reloads the entry so a new interval takes effect."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch("custom_components.denkirs.DenkirsGateway") as gateway_cls:
        _mock_gateway(gateway_cls)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with patch("homeassistant.config_entries.ConfigEntries.async_reload") as reload:
            hass.config_entries.async_update_entry(
                entry, options={CONF_SCAN_INTERVAL: 60}
            )
            await hass.async_block_till_done()

        reload.assert_called_once_with(entry.entry_id)
