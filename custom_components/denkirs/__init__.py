"""The Denkirs smart lighting integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .api import DenkirsGateway, LampAddress
from .const import (
    CONF_CID,
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LAMPS,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import DenkirsCoordinator
from .data import DenkirsConfigEntry, DenkirsRuntimeData
from .models import DenkirsLampConfig


async def async_setup_entry(hass: HomeAssistant, entry: DenkirsConfigEntry) -> bool:
    """Set up Denkirs from a config entry."""
    lamps = _parse_lamps(entry.data[CONF_LAMPS])
    gateway = DenkirsGateway(
        entry.data[CONF_HOST],
        entry.data[CONF_GATEWAY_ID],
        entry.data[CONF_LOCAL_KEY],
    )
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = DenkirsCoordinator(
        hass, entry, gateway, [lamp.address for lamp in lamps], scan_interval
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = DenkirsRuntimeData(
        gateway=gateway, coordinator=coordinator, lamps=lamps
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DenkirsConfigEntry) -> bool:
    """Unload a Denkirs config entry and release its socket."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.gateway.async_disconnect()
    return unloaded


async def _async_reload_on_update(
    hass: HomeAssistant, entry: DenkirsConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _parse_lamps(raw: list[dict[str, Any]]) -> list[DenkirsLampConfig]:
    """Turn stored fixture mappings into typed configs."""
    return [
        DenkirsLampConfig(
            address=LampAddress(device_id=item[CONF_DEVICE_ID], cid=item[CONF_CID]),
            name=item[CONF_NAME],
            model=item.get(CONF_MODEL),
        )
        for item in raw
    ]
