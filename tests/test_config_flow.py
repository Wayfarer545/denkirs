"""Tests for the Denkirs config and options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denkirs.api import DenkirsConnectionError, LampState
from custom_components.denkirs.const import (
    CONF_CID,
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LAMPS,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    DOMAIN,
)

GATEWAY_INPUT = {
    CONF_HOST: "192.168.1.10",
    CONF_GATEWAY_ID: "gwid",
    CONF_LOCAL_KEY: "localkey",
}
LAMP_INPUT = {
    CONF_NAME: "Kitchen",
    CONF_DEVICE_ID: "dev-1",
    CONF_CID: "0018",
    CONF_MODEL: "DK/EU-8003-BK",
    "add_another": False,
}
STATE = LampState(power=True, brightness=500, color_temp=100, mode="white")


def _patch_gateway(*, poll: object) -> object:
    gateway = AsyncMock()
    gateway.async_poll = AsyncMock(side_effect=poll) if poll else AsyncMock()
    gateway.async_disconnect = AsyncMock()
    return patch(
        "custom_components.denkirs.config_flow.DenkirsGateway", return_value=gateway
    )


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GATEWAY_INPUT
    )
    assert result["step_id"] == "lamp"
    return str(result["flow_id"])


async def test_full_flow_creates_entry(hass: HomeAssistant) -> None:
    """A gateway and one fixture produce a config entry."""
    flow_id = await _start(hass)
    with _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(
            flow_id, dict(LAMP_INPUT)
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.168.1.10"
    assert result["data"][CONF_LAMPS] == [
        {
            CONF_NAME: "Kitchen",
            CONF_DEVICE_ID: "dev-1",
            CONF_CID: "0018",
            CONF_MODEL: "DK/EU-8003-BK",
        }
    ]


async def test_flow_collects_multiple_fixtures(hass: HomeAssistant) -> None:
    """The lamp step loops while the user keeps adding fixtures."""
    flow_id = await _start(hass)
    first = {**LAMP_INPUT, "add_another": True}
    result = await hass.config_entries.flow.async_configure(flow_id, first)
    assert result["step_id"] == "lamp"

    second = {
        CONF_NAME: "Hall",
        CONF_DEVICE_ID: "dev-2",
        CONF_CID: "00b8",
        "add_another": False,
    }
    with _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(flow_id, second)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [lamp[CONF_CID] for lamp in result["data"][CONF_LAMPS]] == ["0018", "00b8"]


async def test_unreachable_gateway_reprompts(hass: HomeAssistant) -> None:
    """A fixture that cannot be reached sends the user back to fix the key."""
    flow_id = await _start(hass)
    with _patch_gateway(poll=DenkirsConnectionError("bad key")):
        result = await hass.config_entries.flow.async_configure(
            flow_id, dict(LAMP_INPUT)
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_recovers_after_fixing_the_key(hass: HomeAssistant) -> None:
    """Re-submitting corrected gateway details keeps the collected fixtures."""
    flow_id = await _start(hass)
    with _patch_gateway(poll=DenkirsConnectionError("bad key")):
        result = await hass.config_entries.flow.async_configure(
            flow_id, dict(LAMP_INPUT)
        )
    assert result["step_id"] == "user"

    with _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(flow_id, GATEWAY_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LAMPS][0][CONF_CID] == "0018"


async def test_duplicate_gateway_is_rejected(hass: HomeAssistant) -> None:
    """A gateway that is already configured aborts the flow."""
    MockConfigEntry(domain=DOMAIN, unique_id="gwid", data=GATEWAY_INPUT).add_to_hass(
        hass
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GATEWAY_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_sets_scan_interval(hass: HomeAssistant) -> None:
    """The options flow stores a new scan interval."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="gwid", data=GATEWAY_INPUT)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 60
