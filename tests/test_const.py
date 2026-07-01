"""Sanity checks that keep the manifest and constants in agreement."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.denkirs.const import DOMAIN

MANIFEST_PATH = Path("custom_components/denkirs/manifest.json")


def test_domain_matches_manifest() -> None:
    """The declared domain must match the manifest to keep HA loadable."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["domain"] == DOMAIN


def test_manifest_requires_tinytuya() -> None:
    """The protocol dependency must be pinned in the manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert any(req.startswith("tinytuya==") for req in manifest["requirements"])
