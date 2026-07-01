"""Tests for the Denkirs light platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.util.color import brightness_to_value, value_to_brightness

from custom_components.denkirs.api import LampAddress, LampState
from custom_components.denkirs.const import (
    BRIGHTNESS_SCALE_MAX,
    BRIGHTNESS_SCALE_MIN,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
)
from custom_components.denkirs.data import DenkirsRuntimeData
from custom_components.denkirs.light import (
    DenkirsLight,
    _kelvin_to_native,
    _native_to_kelvin,
    async_setup_entry,
)
from custom_components.denkirs.models import DenkirsLampConfig

ADDRESS = LampAddress(device_id="dev-1", cid="0018")
LAMP = DenkirsLampConfig(address=ADDRESS, name="Kitchen", model="DK/EU-8003-BK")
RANGE = (BRIGHTNESS_SCALE_MIN, BRIGHTNESS_SCALE_MAX)


def _light(state: LampState | None) -> tuple[DenkirsLight, MagicMock]:
    coordinator = MagicMock()
    coordinator.data = {ADDRESS.cid: state} if state is not None else {}
    coordinator.last_update_success = True
    coordinator.async_request_refresh = AsyncMock()
    gateway = AsyncMock()
    gateway.gateway_id = "gw-1"
    return DenkirsLight(coordinator, gateway, LAMP), gateway


def test_reports_state_from_coordinator() -> None:
    """State properties reflect the latest coordinator snapshot."""
    light, _ = _light(
        LampState(power=True, brightness=1000, color_temp=0, mode="white")
    )
    assert light.is_on is True
    assert light.brightness == value_to_brightness(RANGE, 1000)
    assert light.color_temp_kelvin == MIN_COLOR_TEMP_KELVIN
    assert light.available is True


def test_unavailable_when_absent_from_snapshot() -> None:
    """A fixture missing from the snapshot is unavailable with empty state."""
    light, _ = _light(None)
    assert light.available is False
    assert light.is_on is None
    assert light.brightness is None
    assert light.color_temp_kelvin is None


async def test_turn_on_applies_power_only() -> None:
    """A plain turn-on writes only the power state and refreshes."""
    light, gateway = _light(
        LampState(power=False, brightness=None, color_temp=None, mode=None)
    )
    await light.async_turn_on()
    gateway.async_apply.assert_awaited_once_with(
        ADDRESS, power=True, brightness=None, color_temp=None
    )
    light.coordinator.async_request_refresh.assert_awaited_once()


async def test_turn_on_with_brightness_and_color_temp() -> None:
    """Brightness and CCT are converted to native scale in one write."""
    light, gateway = _light(
        LampState(power=True, brightness=500, color_temp=500, mode="white")
    )
    await light.async_turn_on(**{ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000})
    gateway.async_apply.assert_awaited_once_with(
        ADDRESS,
        power=True,
        brightness=round(brightness_to_value(RANGE, 128)),
        color_temp=_kelvin_to_native(4000),
    )


async def test_turn_off_applies_power_false() -> None:
    """Turning off writes the power state and refreshes."""
    light, gateway = _light(
        LampState(power=True, brightness=500, color_temp=500, mode="white")
    )
    await light.async_turn_off()
    gateway.async_apply.assert_awaited_once_with(ADDRESS, power=False)


def test_color_temp_endpoints_map_to_kelvin_bounds() -> None:
    """The native colour-temperature scale spans the fixture's Kelvin range."""
    assert _native_to_kelvin(0) == MIN_COLOR_TEMP_KELVIN
    assert _native_to_kelvin(1000) == MAX_COLOR_TEMP_KELVIN


def test_kelvin_native_round_trip_is_stable() -> None:
    """Converting Kelvin to native and back stays within rounding tolerance."""
    for kelvin in (2700, 4000, 5000, 6500):
        native = _kelvin_to_native(kelvin)
        assert 0 <= native <= 1000
        assert abs(_native_to_kelvin(native) - kelvin) <= 5


def test_kelvin_out_of_range_is_clamped() -> None:
    """Kelvin values beyond the fixture's range clamp to its bounds."""
    assert _kelvin_to_native(2000) == 0
    assert _kelvin_to_native(9000) == 1000


def test_device_metadata_links_to_gateway() -> None:
    """Each fixture is its own device linked to the gateway."""
    light, _ = _light(LampState(power=True, brightness=1000, color_temp=0, mode=None))
    info = light.device_info
    assert info is not None
    assert light.unique_id == "dev-1"
    assert info["identifiers"] == {("denkirs", "dev-1")}
    assert info["via_device"] == ("denkirs", "gw-1")
    assert info["manufacturer"] == "Denkirs"


async def test_setup_entry_adds_one_entity_per_fixture() -> None:
    """The platform creates exactly one entity per configured fixture."""
    gateway = AsyncMock()
    gateway.gateway_id = "gw-1"
    lamps = [LAMP, DenkirsLampConfig(LampAddress("dev-2", "00b8"), "Hall")]
    entry = MagicMock()
    entry.runtime_data = DenkirsRuntimeData(
        gateway=gateway, coordinator=MagicMock(), lamps=lamps
    )
    added: list[DenkirsLight] = []
    await async_setup_entry(MagicMock(), entry, lambda entities: added.extend(entities))

    assert [light.unique_id for light in added] == ["dev-1", "dev-2"]
