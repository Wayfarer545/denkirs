"""Tests for the Denkirs data update coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denkirs.api import (
    DenkirsConnectionError,
    LampAddress,
    LampState,
)
from custom_components.denkirs.const import DOMAIN
from custom_components.denkirs.coordinator import DenkirsCoordinator

LAMP_A = LampAddress(device_id="a", cid="0018")
LAMP_B = LampAddress(device_id="b", cid="00b8")
STATE_A = LampState(power=True, brightness=500, color_temp=100, mode="white")
STATE_B = LampState(power=False, brightness=None, color_temp=None, mode=None)


def _coordinator(
    hass: HomeAssistant, gateway: AsyncMock, lamps: list[LampAddress]
) -> DenkirsCoordinator:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    return DenkirsCoordinator(hass, entry, gateway, lamps, 30)


async def test_update_collects_every_state(hass: HomeAssistant) -> None:
    """A successful poll of both fixtures produces a cid-keyed snapshot."""
    gateway = AsyncMock()
    gateway.async_poll.side_effect = [STATE_A, STATE_B]
    coordinator = _coordinator(hass, gateway, [LAMP_A, LAMP_B])

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data == {"0018": STATE_A, "00b8": STATE_B}


async def test_partial_failure_keeps_healthy_fixtures(hass: HomeAssistant) -> None:
    """One unreachable fixture must not hide the others."""
    gateway = AsyncMock()
    gateway.async_poll.side_effect = [STATE_A, DenkirsConnectionError("no answer")]
    coordinator = _coordinator(hass, gateway, [LAMP_A, LAMP_B])

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data == {"0018": STATE_A}


async def test_total_failure_marks_update_unsuccessful(hass: HomeAssistant) -> None:
    """When no fixture answers, the update is reported as failed."""
    gateway = AsyncMock()
    gateway.async_poll.side_effect = DenkirsConnectionError("gateway dead")
    coordinator = _coordinator(hass, gateway, [LAMP_A, LAMP_B])

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
