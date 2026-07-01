"""Asynchronous client for a Denkirs gateway and its mesh fixtures.

Denkirs SMART track fixtures are Tuya BLE-mesh nodes that live behind a Wi-Fi
gateway. The gateway speaks the local Tuya LAN protocol on port 6668, and each
fixture is addressed through it by its mesh id (``cid``). This module wraps the
synchronous :mod:`tinytuya` client in an async, serialised interface so the rest
of the integration never blocks the event loop and never runs two overlapping
requests on the single gateway socket.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import tinytuya

from .const import (
    DP_BRIGHTNESS,
    DP_COLOR_TEMP,
    DP_MODE,
    DP_POWER,
    PROTOCOL_VERSION,
    TUYA_PORT,
)

_ERROR_KEYS: Final = ("Err", "Error")
_DEFAULT_TIMEOUT: Final = 8
_SCAN_SECONDS: Final = 6


class DenkirsError(Exception):
    """Base error for the Denkirs gateway client."""


class DenkirsConnectionError(DenkirsError):
    """The gateway was unreachable or its response could not be decoded."""


@dataclass(frozen=True, slots=True)
class LampAddress:
    """Immutable address of a fixture behind the gateway."""

    device_id: str
    cid: str


@dataclass(frozen=True, slots=True)
class LampState:
    """Snapshot of a fixture's datapoints on their native scale."""

    power: bool
    brightness: int | None
    color_temp: int | None
    mode: str | None

    @classmethod
    def from_datapoints(cls, dps: Mapping[str, Any]) -> LampState:
        """Build a state from a raw Tuya datapoint mapping."""
        return cls(
            power=bool(dps.get(DP_POWER, False)),
            brightness=_as_int(dps.get(DP_BRIGHTNESS)),
            color_temp=_as_int(dps.get(DP_COLOR_TEMP)),
            mode=_as_str(dps.get(DP_MODE)),
        )


class DenkirsGateway:
    """Async, serialised client for a single Denkirs gateway."""

    def __init__(
        self,
        host: str,
        gateway_id: str,
        local_key: str,
        *,
        port: int = TUYA_PORT,
        version: float = PROTOCOL_VERSION,
    ) -> None:
        """Store connection parameters; sockets are opened lazily on first use."""
        self._host = host
        self._gateway_id = gateway_id
        self._local_key = local_key
        self._port = port
        self._version = version
        self._parent: Any = None
        self._lamps: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def gateway_id(self) -> str:
        """Return the Tuya device id of the gateway."""
        return self._gateway_id

    async def async_poll(self, address: LampAddress) -> LampState:
        """Return the current state of a fixture."""
        return await self._run(address, self._read_state)

    async def async_apply(
        self,
        address: LampAddress,
        *,
        power: bool | None = None,
        brightness: int | None = None,
        color_temp: int | None = None,
    ) -> None:
        """Apply any combination of settings in a single atomic write.

        Brightness and colour temperature are expressed on the device's native
        scale. Passing several settings at once writes them together so the
        fixture never flickers between intermediate states.
        """
        data: dict[str, Any] = {}
        if power is not None:
            data[DP_POWER] = power
        if brightness is not None:
            data[DP_BRIGHTNESS] = brightness
        if color_temp is not None:
            data[DP_COLOR_TEMP] = color_temp
        if data:
            await self._command(address, data)

    async def async_disconnect(self) -> None:
        """Close every socket opened by this client."""
        async with self._lock:
            await asyncio.to_thread(self._close)

    async def _command(self, address: LampAddress, data: dict[str, Any]) -> None:
        await self._run(address, lambda device: _apply(device, data))

    async def _run[T](self, address: LampAddress, action: Callable[[Any], T]) -> T:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._execute, address, action)
            except DenkirsError:
                raise
            except Exception as err:  # tinytuya raises bare Exception subclasses
                raise DenkirsConnectionError(str(err)) from err

    def _execute[T](self, address: LampAddress, action: Callable[[Any], T]) -> T:
        return action(self._lamp(address))

    @staticmethod
    def _read_state(device: Any) -> LampState:
        return LampState.from_datapoints(_datapoints(device.status()))

    def _lamp(self, address: LampAddress) -> Any:
        if self._parent is None:
            self._parent = tinytuya.Device(
                self._gateway_id,
                address=self._host,
                local_key=self._local_key,
                version=self._version,
                port=self._port,
                persist=True,
                connection_timeout=_DEFAULT_TIMEOUT,
            )
        lamp = self._lamps.get(address.cid)
        if lamp is None:
            lamp = tinytuya.Device(
                address.device_id, cid=address.cid, parent=self._parent
            )
            self._lamps[address.cid] = lamp
        return lamp

    def _close(self) -> None:
        for lamp in self._lamps.values():
            lamp.close()
        self._lamps.clear()
        if self._parent is not None:
            self._parent.close()
            self._parent = None


async def async_scan_gateway(gateway_id: str) -> tuple[str, float] | None:
    """Find a gateway's LAN address and protocol version via a broadcast scan.

    Tuya gateways announce themselves over UDP broadcast; the scan matches one
    by its device id and returns its address and protocol version so the setup
    flow never has to ask for them. Returns ``None`` when the gateway does not
    answer within the scan window, so the caller can fall back to manual entry.
    """
    try:
        found = await asyncio.to_thread(_scan)
    except Exception:  # scanning is best-effort; fall back to manual entry
        return None
    info = found.get(gateway_id)
    if not isinstance(info, Mapping) or not info.get("ip"):
        return None
    version = info.get("version")
    return str(info["ip"]), (float(version) if version else PROTOCOL_VERSION)


def _scan() -> Mapping[str, Any]:
    """Broadcast-scan the LAN for Tuya devices, keyed by device id."""
    result = tinytuya.deviceScan(maxretry=_SCAN_SECONDS, poll=False, byID=True)
    return result if isinstance(result, Mapping) else {}


def _apply(device: Any, data: dict[str, Any]) -> None:
    """Write datapoints and validate the acknowledgement (runs off-loop)."""
    _datapoints(device.set_multiple_values(data))


def _as_int(value: Any) -> int | None:
    """Coerce a datapoint value to int, ignoring booleans and non-numerics."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _as_str(value: Any) -> str | None:
    """Return the value only when it is a string."""
    return value if isinstance(value, str) else None


def _datapoints(response: Any) -> Mapping[str, Any]:
    """Extract the datapoint mapping from a Tuya response or raise."""
    if not isinstance(response, Mapping) or any(k in response for k in _ERROR_KEYS):
        msg = f"gateway returned an error: {response!r}"
        raise DenkirsConnectionError(msg)
    dps = response.get("dps")
    if not isinstance(dps, Mapping):
        msg = f"gateway response contained no datapoints: {response!r}"
        raise DenkirsConnectionError(msg)
    return dps
