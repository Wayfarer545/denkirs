"""Constants for the Denkirs integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "denkirs"
MANUFACTURER: Final = "Denkirs"

PLATFORMS: Final = [Platform.LIGHT]

# Configuration keys.
CONF_GATEWAY_ID: Final = "gateway_id"
CONF_LOCAL_KEY: Final = "local_key"
CONF_LAMPS: Final = "lamps"
CONF_CID: Final = "cid"
CONF_DEVICE_ID: Final = "device_id"
CONF_MODEL: Final = "model"

# Cloud-assisted setup keys.
CONF_REGION: Final = "region"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_PROTOCOL_VERSION: Final = "protocol_version"

DEFAULT_REGION: Final = "eu"

# Tuya cloud datacentre region codes mapped to human labels.
TUYA_REGIONS: Final = {
    "eu": "Central Europe",
    "eu-w": "Western Europe",
    "us": "Western America",
    "us-e": "Eastern America",
    "cn": "China",
    "in": "India",
    "sg": "Singapore",
}

# Tuya product categories that are not fixtures (battery wall switches, sensors);
# discovered devices in these categories are left unchecked in the picker.
NON_LIGHT_CATEGORIES: Final = frozenset(
    {"wxkg", "kg", "cz", "pir", "mcs", "wsdcg", "rqbj", "ywbj", "sos", "sj", "ylcg"}
)

# Tuya LAN transport.
PROTOCOL_VERSION: Final = 3.4
TUYA_PORT: Final = 6668

# Datapoints exposed by Denkirs track fixtures (DK/EU-80xx).
DP_POWER: Final = "1"
DP_MODE: Final = "2"
DP_BRIGHTNESS: Final = "3"
DP_COLOR_TEMP: Final = "4"

# Native value ranges reported by the fixtures (Tuya scale).
BRIGHTNESS_SCALE_MIN: Final = 10
BRIGHTNESS_SCALE_MAX: Final = 1000
COLOR_TEMP_SCALE_MIN: Final = 0
COLOR_TEMP_SCALE_MAX: Final = 1000

# Correlated colour temperature span of the tunable-white fixtures.
MIN_COLOR_TEMP_KELVIN: Final = 2700
MAX_COLOR_TEMP_KELVIN: Final = 6500

DEFAULT_SCAN_INTERVAL: Final = 30
