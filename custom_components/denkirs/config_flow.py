"""Config and options flow for the Denkirs integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .api import DenkirsError, DenkirsGateway, LampAddress, async_scan_gateway
from .cloud import (
    DenkirsCloud,
    DenkirsCloudAuthError,
    DenkirsCloudError,
    DenkirsNoGatewaysError,
    DiscoveredFixture,
    DiscoveredGateway,
)
from .const import (
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
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NON_LIGHT_CATEGORIES,
    TUYA_REGIONS,
)
from .data import DenkirsConfigEntry

CONF_ADD_ANOTHER = "add_another"

CLOUD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=DEFAULT_REGION): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=code, label=label)
                    for code, label in TUYA_REGIONS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)

GATEWAY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_GATEWAY_ID): str,
        vol.Required(CONF_LOCAL_KEY): str,
    }
)

GATEWAY_IP_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})

LAMP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_CID): str,
        vol.Optional(CONF_MODEL): str,
        vol.Required(CONF_ADD_ANOTHER, default=False): bool,
    }
)


class DenkirsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guide the user through cloud discovery or manual entry."""

    def __init__(self) -> None:
        """Start with nothing collected yet."""
        self._gateway: dict[str, Any] = {}
        self._lamps: list[dict[str, Any]] = []
        self._creds: dict[str, Any] = {}
        self._version: float | None = None
        self._discovered: list[DiscoveredGateway] = []
        self._selected: DiscoveredGateway | None = None
        self._preselected: set[str] = set()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer cloud discovery or manual entry."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    # -- Cloud path ------------------------------------------------------------

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover gateways and fixtures from a Tuya cloud project."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._creds = user_input
            cloud = DenkirsCloud(
                user_input[CONF_REGION],
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
            )
            try:
                self._discovered = await cloud.async_discover()
            except DenkirsCloudAuthError:
                errors["base"] = "cloud_auth"
            except DenkirsNoGatewaysError:
                errors["base"] = "no_gateways"
            except DenkirsCloudError:
                errors["base"] = "cannot_connect"
            else:
                if len(self._discovered) == 1:
                    self._selected = self._discovered[0]
                    return await self.async_step_fixtures()
                return await self.async_step_gateway_select()
        return self.async_show_form(
            step_id="cloud",
            data_schema=self.add_suggested_values_to_schema(
                CLOUD_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_gateway_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which discovered gateway to configure."""
        if user_input is not None:
            self._selected = next(
                gw
                for gw in self._discovered
                if gw.gateway_id == user_input[CONF_GATEWAY_ID]
            )
            return await self.async_step_fixtures()
        options = [
            selector.SelectOptionDict(value=gw.gateway_id, label=gw.name)
            for gw in self._discovered
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_GATEWAY_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(step_id="gateway_select", data_schema=schema)

    async def async_step_fixtures(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which discovered fixtures to add."""
        gateway = self._selected
        assert gateway is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = set(user_input[CONF_LAMPS])
            if chosen:
                self._lamps = [
                    _fixture_to_lamp(fx) for fx in gateway.fixtures if fx.cid in chosen
                ]
                if self.source == SOURCE_RECONFIGURE:
                    return self._reconfigure_save()
                return await self._async_locate_and_finish(gateway)
            errors["base"] = "no_fixtures"
        return self.async_show_form(
            step_id="fixtures",
            data_schema=self._fixtures_schema(gateway),
            errors=errors,
        )

    def _fixtures_schema(self, gateway: DiscoveredGateway) -> vol.Schema:
        options = [
            selector.SelectOptionDict(value=fx.cid, label=_fixture_label(fx))
            for fx in gateway.fixtures
        ]
        default = [
            fx.cid
            for fx in gateway.fixtures
            if fx.cid in self._preselected
            or (fx.category or "") not in NON_LIGHT_CATEGORIES
        ]
        return vol.Schema(
            {
                vol.Required(CONF_LAMPS, default=default): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )

    async def _async_locate_and_finish(
        self, gateway: DiscoveredGateway
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(gateway.gateway_id)
        self._abort_if_unique_id_configured()
        self._gateway = {
            CONF_GATEWAY_ID: gateway.gateway_id,
            CONF_LOCAL_KEY: gateway.local_key,
        }
        located = await async_scan_gateway(gateway.gateway_id)
        if located is None:
            return await self.async_step_gateway_ip()
        self._gateway[CONF_HOST], self._version = located
        return await self._async_finish_cloud()

    async def async_step_gateway_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the gateway address when the scan did not find it."""
        if user_input is not None:
            self._gateway[CONF_HOST] = user_input[CONF_HOST]
            return await self._async_finish_cloud()
        return self.async_show_form(step_id="gateway_ip", data_schema=GATEWAY_IP_SCHEMA)

    async def _async_finish_cloud(self) -> ConfigFlowResult:
        """Probe the gateway locally, then create the entry or reprompt."""
        if await self._async_cannot_connect(
            self._gateway, self._first_address(), self._version
        ):
            return self.async_show_form(
                step_id="gateway_ip",
                data_schema=self.add_suggested_values_to_schema(
                    GATEWAY_IP_SCHEMA, {CONF_HOST: self._gateway.get(CONF_HOST)}
                ),
                errors={"base": "cannot_connect"},
            )
        assert self._selected is not None
        data = {**self._gateway, CONF_LAMPS: self._lamps, **self._creds}
        if self._version is not None:
            data[CONF_PROTOCOL_VERSION] = self._version
        return self.async_create_entry(title=self._selected.name, data=data)

    # -- Reconfigure (re-sync fixtures from the cloud) -------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-run cloud discovery to refresh the fixture list of an entry."""
        entry = self._get_reconfigure_entry()
        if CONF_CLIENT_ID not in entry.data:
            return self.async_abort(reason="no_cloud_credentials")
        cloud = DenkirsCloud(
            entry.data[CONF_REGION],
            entry.data[CONF_CLIENT_ID],
            entry.data[CONF_CLIENT_SECRET],
        )
        try:
            self._discovered = await cloud.async_discover()
        except DenkirsCloudAuthError:
            return self.async_abort(reason="cloud_auth")
        except DenkirsNoGatewaysError:
            return self.async_abort(reason="no_gateways")
        except DenkirsCloudError:
            return self.async_abort(reason="cannot_connect")
        self._selected = next(
            (
                gw
                for gw in self._discovered
                if gw.gateway_id == entry.data[CONF_GATEWAY_ID]
            ),
            None,
        )
        if self._selected is None:
            return self.async_abort(reason="no_gateways")
        self._preselected = {lamp[CONF_CID] for lamp in entry.data[CONF_LAMPS]}
        return await self.async_step_fixtures()

    def _reconfigure_save(self) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        return self.async_update_reload_and_abort(
            entry, data={**entry.data, CONF_LAMPS: self._lamps}
        )

    # -- Manual path -----------------------------------------------------------

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the gateway connection details by hand."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_GATEWAY_ID])
            self._abort_if_unique_id_configured()
            self._gateway = user_input
            if self._lamps:
                return await self._async_finish_manual()
            return await self.async_step_lamp()
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                GATEWAY_SCHEMA, self._gateway
            ),
        )

    async def async_step_lamp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect one fixture, optionally looping for more."""
        if user_input is not None:
            add_another = user_input.pop(CONF_ADD_ANOTHER)
            self._lamps.append(user_input)
            if add_another:
                return await self.async_step_lamp()
            return await self._async_finish_manual()
        return self.async_show_form(step_id="lamp", data_schema=LAMP_SCHEMA)

    async def _async_finish_manual(self) -> ConfigFlowResult:
        """Validate connectivity, then create the entry or reprompt."""
        if await self._async_cannot_connect(self._gateway, self._first_address()):
            return self.async_show_form(
                step_id="manual",
                data_schema=self.add_suggested_values_to_schema(
                    GATEWAY_SCHEMA, self._gateway
                ),
                errors={"base": "cannot_connect"},
            )
        return self.async_create_entry(
            title=self._gateway[CONF_HOST],
            data={**self._gateway, CONF_LAMPS: self._lamps},
        )

    # -- Shared helpers --------------------------------------------------------

    def _first_address(self) -> LampAddress:
        first = self._lamps[0]
        return LampAddress(device_id=first[CONF_DEVICE_ID], cid=first[CONF_CID])

    async def _async_cannot_connect(
        self,
        gateway_conf: dict[str, Any],
        address: LampAddress,
        version: float | None = None,
    ) -> bool:
        """Return True if the gateway does not answer for the fixture."""
        if version is None:
            gateway = DenkirsGateway(
                gateway_conf[CONF_HOST],
                gateway_conf[CONF_GATEWAY_ID],
                gateway_conf[CONF_LOCAL_KEY],
            )
        else:
            gateway = DenkirsGateway(
                gateway_conf[CONF_HOST],
                gateway_conf[CONF_GATEWAY_ID],
                gateway_conf[CONF_LOCAL_KEY],
                version=version,
            )
        try:
            await gateway.async_poll(address)
        except DenkirsError:
            return True
        finally:
            await gateway.async_disconnect()
        return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: DenkirsConfigEntry,
    ) -> DenkirsOptionsFlow:
        """Return the options flow handler."""
        return DenkirsOptionsFlow()


class DenkirsOptionsFlow(OptionsFlow):
    """Let the user tune the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the scan interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        interval = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5,
                max=600,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema = vol.Schema(
            {vol.Required(CONF_SCAN_INTERVAL, default=current): interval}
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _fixture_to_lamp(fixture: DiscoveredFixture) -> dict[str, Any]:
    """Turn a discovered fixture into the stored lamp mapping."""
    lamp: dict[str, Any] = {
        CONF_NAME: fixture.name,
        CONF_DEVICE_ID: fixture.device_id,
        CONF_CID: fixture.cid,
    }
    if fixture.model:
        lamp[CONF_MODEL] = fixture.model
    return lamp


def _fixture_label(fixture: DiscoveredFixture) -> str:
    """Return a picker label for a discovered fixture."""
    return f"{fixture.name} — {fixture.model}" if fixture.model else fixture.name
