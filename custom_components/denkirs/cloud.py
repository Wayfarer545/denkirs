"""Tuya Cloud discovery for zero-touch Denkirs setup.

The setup flow can pull the entire fixture inventory from a Tuya IoT cloud
project instead of asking the installer to type device ids and keys by hand.
This module wraps the synchronous :mod:`tinytuya` cloud client in an async
interface and turns its flat device list into gateways and the fixtures that
live behind them. It is used only during configuration; runtime control stays
entirely local.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import tinytuya

from .api import DenkirsError


class DenkirsCloudError(DenkirsError):
    """Tuya Cloud discovery failed."""


class DenkirsCloudAuthError(DenkirsCloudError):
    """The Tuya Cloud credentials were rejected."""


class DenkirsNoGatewaysError(DenkirsCloudError):
    """The account holds no gateway with fixtures behind it."""


@dataclass(frozen=True, slots=True)
class DiscoveredFixture:
    """A fixture found behind a gateway in the cloud inventory."""

    device_id: str
    cid: str
    name: str
    model: str | None
    category: str | None


@dataclass(frozen=True, slots=True)
class DiscoveredGateway:
    """A gateway and the fixtures discovered behind it."""

    gateway_id: str
    local_key: str
    name: str
    fixtures: list[DiscoveredFixture]


class DenkirsCloud:
    """Discover Denkirs gateways and fixtures from a Tuya IoT project."""

    def __init__(self, region: str, client_id: str, client_secret: str) -> None:
        """Store the cloud credentials; the client is built on discovery."""
        self._region = region
        self._client_id = client_id
        self._client_secret = client_secret

    async def async_discover(self) -> list[DiscoveredGateway]:
        """Return every gateway with its fixtures, or raise on failure."""
        return await asyncio.to_thread(self._discover)

    def _discover(self) -> list[DiscoveredGateway]:
        cloud = self._connect()
        gateways = _partition(_device_list(cloud))
        if not gateways:
            msg = "the account holds no gateway with fixtures behind it"
            raise DenkirsNoGatewaysError(msg)
        return gateways

    def _connect(self) -> Any:
        try:
            client = tinytuya.Cloud(self._region, self._client_id, self._client_secret)
        except Exception as err:  # tinytuya raises bare exceptions on bad input
            raise DenkirsCloudAuthError(str(err)) from err
        if not client.token:
            msg = _message(client.error) or "the cloud credentials were rejected"
            raise DenkirsCloudAuthError(msg)
        return client


def _device_list(cloud: Any) -> list[dict[str, Any]]:
    devices = cloud.getdevices()
    if not isinstance(devices, list):
        msg = _message(devices) or "the cloud device list could not be read"
        raise DenkirsCloudError(msg)
    return devices


def _partition(devices: list[dict[str, Any]]) -> list[DiscoveredGateway]:
    by_id = {dev["id"]: dev for dev in devices if "id" in dev}
    children: dict[str, list[dict[str, Any]]] = {}
    for dev in devices:
        parent = dev.get("gateway_id")
        if parent and dev.get("node_id"):
            children.setdefault(parent, []).append(dev)

    gateways: list[DiscoveredGateway] = []
    for gateway_id, subs in children.items():
        parent = by_id.get(gateway_id)
        if parent is None:
            continue
        fixtures = _fixtures(subs, by_id)
        if fixtures:
            gateways.append(
                DiscoveredGateway(
                    gateway_id=gateway_id,
                    local_key=str(parent.get("key", "")),
                    name=str(parent.get("name") or gateway_id),
                    fixtures=fixtures,
                )
            )
    return gateways


def _fixtures(
    subs: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]
) -> list[DiscoveredFixture]:
    fixtures: list[DiscoveredFixture] = []
    for sub in subs:
        if sub.get("id") and sub.get("node_id"):
            fixtures.append(_fixture(sub, by_id.get(sub["id"], {})))
    return fixtures


def _fixture(sub: dict[str, Any], extra: dict[str, Any]) -> DiscoveredFixture:
    device_id = str(sub["id"])
    model = (
        sub.get("product_name")
        or extra.get("model")
        or extra.get("product_name")
        or sub.get("product_id")
    )
    return DiscoveredFixture(
        device_id=device_id,
        cid=str(sub["node_id"]),
        name=str(sub.get("name") or extra.get("name") or device_id),
        model=str(model) if model else None,
        category=sub.get("category") or extra.get("category"),
    )


def _message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("Error") or payload.get("msg")
        return str(value) if value else None
    return None
