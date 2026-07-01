"""Config and options flow for the Denkirs integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .api import DenkirsError, DenkirsGateway, LampAddress
from .const import (
    CONF_CID,
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LAMPS,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .data import DenkirsConfigEntry

CONF_ADD_ANOTHER = "add_another"

GATEWAY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_GATEWAY_ID): str,
        vol.Required(CONF_LOCAL_KEY): str,
    }
)

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
    """Guide the user through pairing a gateway and its fixtures."""

    def __init__(self) -> None:
        """Start with no gateway and no fixtures collected."""
        self._gateway: dict[str, Any] = {}
        self._lamps: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the gateway connection details."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_GATEWAY_ID])
            self._abort_if_unique_id_configured()
            self._gateway = user_input
            if self._lamps:
                return await self._async_finish()
            return await self.async_step_lamp()
        return self.async_show_form(
            step_id="user",
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
            return await self._async_finish()
        return self.async_show_form(step_id="lamp", data_schema=LAMP_SCHEMA)

    async def _async_finish(self) -> ConfigFlowResult:
        """Validate connectivity, then create the entry or reprompt."""
        if await self._async_cannot_connect():
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(
                    GATEWAY_SCHEMA, self._gateway
                ),
                errors={"base": "cannot_connect"},
            )
        return self.async_create_entry(
            title=self._gateway[CONF_HOST],
            data={**self._gateway, CONF_LAMPS: self._lamps},
        )

    async def _async_cannot_connect(self) -> bool:
        """Return True if the gateway does not answer for the first fixture."""
        gateway = DenkirsGateway(
            self._gateway[CONF_HOST],
            self._gateway[CONF_GATEWAY_ID],
            self._gateway[CONF_LOCAL_KEY],
        )
        first = self._lamps[0]
        address = LampAddress(device_id=first[CONF_DEVICE_ID], cid=first[CONF_CID])
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
