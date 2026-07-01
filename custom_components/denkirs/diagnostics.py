"""Diagnostics support for the Denkirs integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_SECRET, CONF_LOCAL_KEY
from .data import DenkirsConfigEntry

TO_REDACT = {CONF_LOCAL_KEY, CONF_CLIENT_SECRET}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DenkirsConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": dict(entry.options),
        },
        "fixtures": {
            cid: {
                "power": state.power,
                "brightness": state.brightness,
                "color_temp": state.color_temp,
                "mode": state.mode,
            }
            for cid, state in coordinator.data.items()
        },
    }
