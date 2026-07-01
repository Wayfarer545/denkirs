"""Runtime data carried on a Denkirs config entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .api import DenkirsGateway
from .coordinator import DenkirsCoordinator
from .models import DenkirsLampConfig


@dataclass(slots=True)
class DenkirsRuntimeData:
    """Objects shared between the setup entry and its platforms."""

    gateway: DenkirsGateway
    coordinator: DenkirsCoordinator
    lamps: list[DenkirsLampConfig]


type DenkirsConfigEntry = ConfigEntry[DenkirsRuntimeData]
