"""Tests for the Denkirs config and options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denkirs.api import DenkirsConnectionError, LampState
from custom_components.denkirs.cloud import (
    DenkirsCloudAuthError,
    DenkirsCloudError,
    DenkirsNoGatewaysError,
    DiscoveredFixture,
    DiscoveredGateway,
)
from custom_components.denkirs.const import (
    CONF_CID,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LAMPS,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    CONF_PROTOCOL_VERSION,
    CONF_REGION,
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
CLOUD_INPUT = {
    CONF_REGION: "eu",
    CONF_CLIENT_ID: "cid",
    CONF_CLIENT_SECRET: "secret",
}
STATE = LampState(power=True, brightness=500, color_temp=100, mode="white")

GATEWAY = DiscoveredGateway(
    gateway_id="gwid",
    local_key="localkey",
    name="Hub",
    fixtures=[
        DiscoveredFixture("dev-1", "0018", "Kitchen", "DK/EU-8003-BK", "dj"),
        DiscoveredFixture("dev-2", "00b8", "Hall", None, "dj"),
    ],
)
GATEWAY_2 = DiscoveredGateway(
    gateway_id="gw2",
    local_key="k2",
    name="Hub 2",
    fixtures=[DiscoveredFixture("dev-9", "00c0", "Bath", None, "dj")],
)


def _patch_gateway(*, poll: object) -> object:
    gateway = AsyncMock()
    gateway.async_poll = AsyncMock(side_effect=poll) if poll else AsyncMock()
    gateway.async_disconnect = AsyncMock()
    return patch(
        "custom_components.denkirs.config_flow.DenkirsGateway", return_value=gateway
    )


def _patch_cloud(*, discover: object) -> object:
    cloud = AsyncMock()
    if isinstance(discover, Exception):
        cloud.async_discover = AsyncMock(side_effect=discover)
    else:
        cloud.async_discover = AsyncMock(return_value=discover)
    return patch(
        "custom_components.denkirs.config_flow.DenkirsCloud", return_value=cloud
    )


def _patch_scan(result: object) -> object:
    return patch(
        "custom_components.denkirs.config_flow.async_scan_gateway",
        AsyncMock(return_value=result),
    )


async def _menu(hass: HomeAssistant, choice: str) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": choice}
    )


async def _start_manual(hass: HomeAssistant) -> str:
    result = await _menu(hass, "manual")
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GATEWAY_INPUT
    )
    assert result["step_id"] == "lamp"
    return str(result["flow_id"])


# -- Manual path -------------------------------------------------------------


async def test_full_flow_creates_entry(hass: HomeAssistant) -> None:
    """A gateway and one fixture produce a config entry."""
    flow_id = await _start_manual(hass)
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
    flow_id = await _start_manual(hass)
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
    flow_id = await _start_manual(hass)
    with _patch_gateway(poll=DenkirsConnectionError("bad key")):
        result = await hass.config_entries.flow.async_configure(
            flow_id, dict(LAMP_INPUT)
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_recovers_after_fixing_the_key(hass: HomeAssistant) -> None:
    """Re-submitting corrected gateway details keeps the collected fixtures."""
    flow_id = await _start_manual(hass)
    with _patch_gateway(poll=DenkirsConnectionError("bad key")):
        result = await hass.config_entries.flow.async_configure(
            flow_id, dict(LAMP_INPUT)
        )
    assert result["step_id"] == "manual"

    with _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(flow_id, GATEWAY_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LAMPS][0][CONF_CID] == "0018"


async def test_duplicate_gateway_is_rejected(hass: HomeAssistant) -> None:
    """A gateway that is already configured aborts the flow."""
    MockConfigEntry(domain=DOMAIN, unique_id="gwid", data=GATEWAY_INPUT).add_to_hass(
        hass
    )
    result = await _menu(hass, "manual")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GATEWAY_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# -- Cloud path --------------------------------------------------------------


async def test_cloud_flow_discovers_and_creates_entry(hass: HomeAssistant) -> None:
    """A single discovered gateway skips selection and creates the entry."""
    result = await _menu(hass, "cloud")
    assert result["step_id"] == "cloud"

    with _patch_cloud(discover=[GATEWAY]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )
    assert result["step_id"] == "fixtures"

    with _patch_scan(("192.168.1.10", 3.4)), _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LAMPS: ["0018", "00b8"]}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_HOST] == "192.168.1.10"
    assert data[CONF_GATEWAY_ID] == "gwid"
    assert data[CONF_LOCAL_KEY] == "localkey"
    assert [lamp[CONF_CID] for lamp in data[CONF_LAMPS]] == ["0018", "00b8"]
    assert data[CONF_CLIENT_SECRET] == "secret"
    assert data[CONF_PROTOCOL_VERSION] == 3.4


async def test_cloud_flow_selects_gateway_when_multiple(hass: HomeAssistant) -> None:
    """Several gateways add a selection step before fixtures."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=[GATEWAY, GATEWAY_2]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )
    assert result["step_id"] == "gateway_select"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_GATEWAY_ID: "gw2"}
    )
    assert result["step_id"] == "fixtures"

    with _patch_scan(("192.168.1.11", 3.4)), _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LAMPS: ["00c0"]}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GATEWAY_ID] == "gw2"


async def test_cloud_flow_asks_for_ip_when_scan_fails(hass: HomeAssistant) -> None:
    """A failed LAN scan falls back to manual address entry."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=[GATEWAY]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )

    with _patch_scan(None), _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LAMPS: ["0018"]}
        )
    assert result["step_id"] == "gateway_ip"

    with _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.1.50"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.168.1.50"
    assert CONF_PROTOCOL_VERSION not in result["data"]


async def test_cloud_flow_shows_error_on_bad_credentials(hass: HomeAssistant) -> None:
    """Rejected credentials keep the user on the cloud form."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=DenkirsCloudAuthError("bad")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "cloud_auth"}


async def test_cloud_flow_reports_when_no_gateways(hass: HomeAssistant) -> None:
    """An account without a gateway shows a friendly error."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=DenkirsNoGatewaysError("none")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )

    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "no_gateways"}


async def test_cloud_flow_reports_generic_cloud_failure(hass: HomeAssistant) -> None:
    """Any other cloud failure keeps the user on the cloud form."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=DenkirsCloudError("boom")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )

    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_cloud_flow_reprompts_when_probe_fails(hass: HomeAssistant) -> None:
    """A located gateway that fails the local probe asks to confirm the address."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=[GATEWAY]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )

    with (
        _patch_scan(("192.168.1.10", 3.4)),
        _patch_gateway(poll=DenkirsConnectionError("bad key")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LAMPS: ["0018"]}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_ip"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_cloud_flow_requires_a_fixture(hass: HomeAssistant) -> None:
    """Selecting no fixture reprompts on the fixtures step."""
    result = await _menu(hass, "cloud")
    with _patch_cloud(discover=[GATEWAY]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LAMPS: []}
    )
    assert result["step_id"] == "fixtures"
    assert result["errors"] == {"base": "no_fixtures"}


# -- Reconfigure -------------------------------------------------------------

RECONFIGURE_DATA = {
    **GATEWAY_INPUT,
    CONF_LAMPS: [{CONF_NAME: "Kitchen", CONF_DEVICE_ID: "dev-1", CONF_CID: "0018"}],
    CONF_REGION: "eu",
    CONF_CLIENT_ID: "cid",
    CONF_CLIENT_SECRET: "secret",
}


async def test_reconfigure_resyncs_fixtures(hass: HomeAssistant) -> None:
    """Reconfigure re-runs discovery and rewrites the fixture list."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="gwid", data=RECONFIGURE_DATA)
    entry.add_to_hass(hass)

    with _patch_cloud(discover=[GATEWAY]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
    assert result["step_id"] == "fixtures"

    with _patch_gateway(poll=[STATE]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LAMPS: ["0018", "00b8"]}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert [lamp[CONF_CID] for lamp in entry.data[CONF_LAMPS]] == ["0018", "00b8"]


async def test_reconfigure_without_cloud_credentials_aborts(
    hass: HomeAssistant,
) -> None:
    """A manually configured entry cannot be re-synced from the cloud."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="gwid",
        data={
            **GATEWAY_INPUT,
            CONF_LAMPS: [
                {CONF_NAME: "Kitchen", CONF_DEVICE_ID: "dev-1", CONF_CID: "0018"}
            ],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_cloud_credentials"


async def _reconfigure(hass: HomeAssistant, discover: object) -> dict:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="gwid", data=RECONFIGURE_DATA)
    entry.add_to_hass(hass)
    with _patch_cloud(discover=discover):
        return await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )


async def test_reconfigure_aborts_on_auth_error(hass: HomeAssistant) -> None:
    """Rejected stored credentials abort the re-sync."""
    result = await _reconfigure(hass, DenkirsCloudAuthError("x"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cloud_auth"


async def test_reconfigure_aborts_when_account_has_no_gateways(
    hass: HomeAssistant,
) -> None:
    """An empty account aborts the re-sync."""
    result = await _reconfigure(hass, DenkirsNoGatewaysError("none"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_gateways"


async def test_reconfigure_aborts_on_cloud_error(hass: HomeAssistant) -> None:
    """A cloud failure aborts the re-sync."""
    result = await _reconfigure(hass, DenkirsCloudError("boom"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_reconfigure_aborts_when_gateway_missing(hass: HomeAssistant) -> None:
    """The entry's gateway no longer being in the account aborts the re-sync."""
    result = await _reconfigure(hass, [GATEWAY_2])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_gateways"


# -- Options -----------------------------------------------------------------


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
