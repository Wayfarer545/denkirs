"""Tests for Tuya cloud discovery and LAN scanning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.denkirs.api import async_scan_gateway
from custom_components.denkirs.cloud import (
    DenkirsCloud,
    DenkirsCloudAuthError,
    DenkirsCloudError,
    DenkirsNoGatewaysError,
)

GATEWAY_DEV = {
    "id": "gwid",
    "name": "Hub",
    "key": "localkey",
    "sub": True,
    "gateway_id": "",
    "category": "wg2",
}
LAMP_A = {
    "id": "dev-1",
    "name": "Kitchen",
    "sub": True,
    "gateway_id": "gwid",
    "node_id": "0018",
    "product_name": "DK/EU-8003-BK",
    "category": "dj",
}
LAMP_B = {
    "id": "dev-2",
    "name": "Hall",
    "sub": True,
    "gateway_id": "gwid",
    "node_id": "00b8",
    "category": "dj",
}
LAMP_C = {
    "id": "dev-3",
    "name": "Bed",
    "sub": True,
    "gateway_id": "gwid",
    "node_id": "00c8",
    "model": "MDL",
    "category": "dj",
}


def _cloud_client(
    *, token: object = "tok", devices: object = None, error: object = None
) -> MagicMock:
    client = MagicMock()
    client.token = token
    client.error = error
    client.getdevices.return_value = [] if devices is None else devices
    return client


def _patch(client: MagicMock) -> object:
    tuya = MagicMock()
    tuya.Cloud.return_value = client
    return patch("custom_components.denkirs.cloud.tinytuya", tuya)


async def _discover(client: MagicMock) -> list:
    with _patch(client):
        return await DenkirsCloud("eu", "id", "secret").async_discover()


async def test_discover_partitions_gateway_and_fixtures() -> None:
    """The flat device list becomes a gateway with its fixtures."""
    gateways = await _discover(
        _cloud_client(devices=[GATEWAY_DEV, LAMP_A, LAMP_B, LAMP_C])
    )
    assert len(gateways) == 1
    gateway = gateways[0]
    assert gateway.gateway_id == "gwid"
    assert gateway.local_key == "localkey"
    assert gateway.name == "Hub"
    assert [(f.cid, f.device_id) for f in gateway.fixtures] == [
        ("0018", "dev-1"),
        ("00b8", "dev-2"),
        ("00c8", "dev-3"),
    ]
    assert [f.model for f in gateway.fixtures] == ["DK/EU-8003-BK", None, "MDL"]


async def test_discover_keeps_non_light_devices() -> None:
    """Discovery is lossless; a switch is returned with its category."""
    switch = {
        "id": "sw-1",
        "name": "Switch",
        "sub": True,
        "gateway_id": "gwid",
        "node_id": "00d0",
        "category": "wxkg",
    }
    gateways = await _discover(_cloud_client(devices=[GATEWAY_DEV, LAMP_A, switch]))
    categories = {f.cid: f.category for f in gateways[0].fixtures}
    assert categories == {"0018": "dj", "00d0": "wxkg"}


async def test_discover_skips_fixture_without_node_id() -> None:
    """A sub-device missing its node id is ignored."""
    bad = {"id": "dev-x", "name": "Bad", "sub": True, "gateway_id": "gwid"}
    gateways = await _discover(_cloud_client(devices=[GATEWAY_DEV, LAMP_A, bad]))
    assert [f.cid for f in gateways[0].fixtures] == ["0018"]


async def test_discover_resolves_model_from_product_id() -> None:
    """A fixture without a product name falls back to its product id."""
    lamp = {
        "id": "dev-9",
        "name": "Desk",
        "sub": True,
        "gateway_id": "gwid",
        "node_id": "00e0",
        "product_id": "pid",
    }
    gateways = await _discover(_cloud_client(devices=[GATEWAY_DEV, lamp]))
    assert gateways[0].fixtures[0].model == "pid"


async def test_discover_raises_auth_error_when_token_missing() -> None:
    """A missing token means the credentials were rejected."""
    with pytest.raises(DenkirsCloudAuthError):
        await _discover(_cloud_client(token=None, error=None))


async def test_discover_raises_auth_error_when_construction_fails() -> None:
    """A tinytuya constructor error surfaces as an auth error."""
    tuya = MagicMock()
    tuya.Cloud.side_effect = TypeError("Tuya Cloud Key and Secret required")
    with (
        patch("custom_components.denkirs.cloud.tinytuya", tuya),
        pytest.raises(DenkirsCloudAuthError),
    ):
        await DenkirsCloud("eu", "", "").async_discover()


async def test_discover_raises_when_device_list_is_an_error() -> None:
    """A non-list device response is a cloud error."""
    with pytest.raises(DenkirsCloudError):
        await _discover(_cloud_client(devices={"Error": "nope"}))


async def test_discover_raises_when_gateway_absent_from_account() -> None:
    """A fixture whose parent gateway is missing from the list raises."""
    orphan = {"id": "dev-1", "sub": True, "gateway_id": "ghost", "node_id": "0018"}
    with pytest.raises(DenkirsNoGatewaysError):
        await _discover(_cloud_client(devices=[orphan]))


async def test_discover_ignores_gateway_without_valid_fixtures() -> None:
    """A gateway whose only child lacks a device id yields no fixtures."""
    child = {"sub": True, "gateway_id": "gwid", "node_id": "0018"}
    with pytest.raises(DenkirsNoGatewaysError):
        await _discover(_cloud_client(devices=[GATEWAY_DEV, child]))


def _patch_scan(result: object) -> object:
    tuya = MagicMock()
    tuya.deviceScan.return_value = result
    return patch("custom_components.denkirs.api.tinytuya", tuya)


async def test_scan_finds_gateway_address() -> None:
    """A matching broadcast yields the address and protocol version."""
    with _patch_scan({"gwid": {"ip": "192.168.1.10", "version": 3.4}}):
        assert await async_scan_gateway("gwid") == ("192.168.1.10", 3.4)


async def test_scan_defaults_version_when_absent() -> None:
    """A broadcast without a version falls back to the default."""
    with _patch_scan({"gwid": {"ip": "192.168.1.10"}}):
        assert await async_scan_gateway("gwid") == ("192.168.1.10", 3.4)


async def test_scan_returns_none_when_gateway_absent() -> None:
    """A gateway that never answers yields no address."""
    with _patch_scan({"other": {"ip": "1.2.3.4"}}):
        assert await async_scan_gateway("gwid") is None


async def test_scan_returns_none_without_ip() -> None:
    """A broadcast entry lacking an address is ignored."""
    with _patch_scan({"gwid": {"version": 3.3}}):
        assert await async_scan_gateway("gwid") is None


async def test_scan_handles_non_mapping_result() -> None:
    """A malformed scan result yields no address."""
    with _patch_scan(None):
        assert await async_scan_gateway("gwid") is None


async def test_scan_returns_none_on_error() -> None:
    """A scanner exception is swallowed so setup can fall back."""
    tuya = MagicMock()
    tuya.deviceScan.side_effect = OSError("no network")
    with patch("custom_components.denkirs.api.tinytuya", tuya):
        assert await async_scan_gateway("gwid") is None
