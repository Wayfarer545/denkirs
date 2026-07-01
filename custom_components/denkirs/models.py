"""Domain value objects shared across the Denkirs integration."""

from __future__ import annotations

from dataclasses import dataclass

from .api import LampAddress


@dataclass(frozen=True, slots=True)
class DenkirsLampConfig:
    """A configured fixture: how to reach it and how to present it."""

    address: LampAddress
    name: str
    model: str | None = None
