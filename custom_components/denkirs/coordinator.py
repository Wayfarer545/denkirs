"""Data update coordinator for a Denkirs gateway."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DenkirsError, DenkirsGateway, LampAddress, LampState
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type LampStates = dict[str, LampState]


class DenkirsCoordinator(DataUpdateCoordinator[LampStates]):
    """Poll every fixture behind a single gateway on a fixed interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        gateway: DenkirsGateway,
        lamps: list[LampAddress],
        scan_interval: int,
    ) -> None:
        """Bind the coordinator to a gateway and the fixtures it serves."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.gateway = gateway
        self.lamps = lamps

    async def _async_update_data(self) -> LampStates:
        """Poll each fixture, tolerating individual failures.

        A fixture that does not answer is simply omitted from the snapshot so
        its entity becomes unavailable while its healthy peers keep updating.
        Only a total blackout — every fixture failing — is escalated so Home
        Assistant marks the whole device unavailable.
        """
        states: LampStates = {}
        last_error: DenkirsError | None = None
        for lamp in self.lamps:
            try:
                states[lamp.cid] = await self.gateway.async_poll(lamp)
            except DenkirsError as err:
                last_error = err
                _LOGGER.debug("Polling fixture %s failed: %s", lamp.cid, err)
        if not states and last_error is not None:
            raise UpdateFailed(str(last_error)) from last_error
        return states
