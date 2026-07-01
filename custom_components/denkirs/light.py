"""Light platform for Denkirs track fixtures."""

from __future__ import annotations

from typing import Any, Final

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .api import LampState
from .const import (
    BRIGHTNESS_SCALE_MAX,
    BRIGHTNESS_SCALE_MIN,
    COLOR_TEMP_SCALE_MAX,
    COLOR_TEMP_SCALE_MIN,
    DOMAIN,
    MANUFACTURER,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
)
from .coordinator import DenkirsCoordinator
from .data import DenkirsConfigEntry
from .models import DenkirsLampConfig

_BRIGHTNESS_RANGE: Final = (BRIGHTNESS_SCALE_MIN, BRIGHTNESS_SCALE_MAX)
_NATIVE_CCT_SPAN: Final = COLOR_TEMP_SCALE_MAX - COLOR_TEMP_SCALE_MIN
_KELVIN_SPAN: Final = MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenkirsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Denkirs fixtures from a config entry."""
    data = entry.runtime_data
    async_add_entities(
        DenkirsLight(data.coordinator, data.gateway, lamp) for lamp in data.lamps
    )


class DenkirsLight(CoordinatorEntity[DenkirsCoordinator], LightEntity):
    """A single tunable-white Denkirs track fixture."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

    def __init__(
        self,
        coordinator: DenkirsCoordinator,
        gateway: Any,
        lamp: DenkirsLampConfig,
    ) -> None:
        """Initialise the entity for one configured fixture."""
        super().__init__(coordinator)
        self._gateway = gateway
        self._address = lamp.address
        self._attr_unique_id = lamp.address.device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, lamp.address.device_id)},
            name=lamp.name,
            manufacturer=MANUFACTURER,
            model=lamp.model,
            via_device=(DOMAIN, gateway.gateway_id),
        )

    @property
    def _state(self) -> LampState | None:
        return self.coordinator.data.get(self._address.cid)

    @property
    def available(self) -> bool:
        """Return True only while the fixture answered the latest poll."""
        return super().available and self._state is not None

    @property
    def is_on(self) -> bool | None:
        """Return whether the fixture is on."""
        state = self._state
        return state.power if state is not None else None

    @property
    def brightness(self) -> int | None:
        """Return brightness on Home Assistant's 0-255 scale."""
        state = self._state
        if state is None or state.brightness is None:
            return None
        return value_to_brightness(_BRIGHTNESS_RANGE, state.brightness)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the colour temperature in Kelvin."""
        state = self._state
        if state is None or state.color_temp is None:
            return None
        return _native_to_kelvin(state.color_temp)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the fixture on, applying any requested brightness or CCT."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        await self._gateway.async_apply(
            self._address,
            power=True,
            brightness=(
                round(brightness_to_value(_BRIGHTNESS_RANGE, brightness))
                if brightness is not None
                else None
            ),
            color_temp=_kelvin_to_native(kelvin) if kelvin is not None else None,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fixture off."""
        await self._gateway.async_apply(self._address, power=False)
        await self.coordinator.async_request_refresh()


def _native_to_kelvin(native: int) -> int:
    """Map the device's 0-1000 warm-to-cool scale to Kelvin."""
    fraction = (native - COLOR_TEMP_SCALE_MIN) / _NATIVE_CCT_SPAN
    return round(MIN_COLOR_TEMP_KELVIN + fraction * _KELVIN_SPAN)


def _kelvin_to_native(kelvin: int) -> int:
    """Map a Kelvin value onto the device's 0-1000 scale, clamped to range."""
    fraction = min(1.0, max(0.0, (kelvin - MIN_COLOR_TEMP_KELVIN) / _KELVIN_SPAN))
    return round(COLOR_TEMP_SCALE_MIN + fraction * _NATIVE_CCT_SPAN)
