"""Guardrails for the vendored Ultimate Space Kit (Poly Pizza / Quaternius).

The 87-asset kit is ~11 MiB on disk, licensed CC0. Two failure modes to
catch early:

1. The manifest drifts from the files on disk — a path listed in
   ``manifest.json`` no longer resolves, so the scene will 404 at runtime.
2. Someone quietly precaches a kit model in the service worker, bloating
   the install footprint past the mobile budget the runtime_policy warns
   against.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT_DIR = ROOT / "assets" / "poly-pizza" / "ultimate-space-kit"
MANIFEST = KIT_DIR / "manifest.json"
SW_JS = ROOT / "web" / "frontend" / "sw.js"

_ASSET_REQUIRED = {"id", "title", "filename", "path", "bytes", "category"}
_TOP_REQUIRED = {
    "id",
    "title",
    "creator",
    "license",
    "format",
    "asset_count",
    "total_bytes",
    "assets",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_top_level_shape(manifest: dict) -> None:
    missing = _TOP_REQUIRED - manifest.keys()
    assert not missing, f"manifest missing keys: {missing}"
    assert manifest["id"] == "ultimate-space-kit"
    assert manifest["format"] == "glb"
    assert manifest["license"].startswith("CC0")
    assert isinstance(manifest["assets"], list)
    assert manifest["asset_count"] == len(manifest["assets"])


def test_every_asset_path_exists_on_disk(manifest: dict) -> None:
    missing: list[str] = []
    for asset in manifest["assets"]:
        missing_keys = _ASSET_REQUIRED - asset.keys()
        assert not missing_keys, f"asset {asset.get('id')!r} missing: {missing_keys}"
        assert asset["path"].startswith("/assets/poly-pizza/ultimate-space-kit/")
        on_disk = ROOT / unquote(asset["path"]).lstrip("/")
        if not on_disk.is_file():
            missing.append(asset["path"])
    assert not missing, f"manifest paths not on disk: {missing[:5]}"


def test_manifest_bytes_match_disk_within_tolerance(manifest: dict) -> None:
    """Sum of per-asset bytes should match total_bytes and real file sizes.

    Guards against half-updated manifests where someone re-ran a refresh
    on only a subset of models.
    """
    summed = sum(a["bytes"] for a in manifest["assets"])
    assert summed == manifest["total_bytes"]
    # Spot-check: pick the first 3 assets and confirm disk size matches.
    for asset in manifest["assets"][:3]:
        on_disk = ROOT / unquote(asset["path"]).lstrip("/")
        assert on_disk.stat().st_size == asset["bytes"], asset["path"]


def test_no_kit_model_is_in_service_worker_precache() -> None:
    """The kit must stay out of the SW precache — mobile first-frame budget."""
    sw_text = SW_JS.read_text(encoding="utf-8")
    assert "ultimate-space-kit" not in sw_text
    assert "/poly-pizza/" not in sw_text
