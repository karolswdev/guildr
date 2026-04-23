"""Rate-card snapshot immutability tests for local cost profiles."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.lib.local_cost import load_local_cost_profile


def _rate_dir(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "costs" / "rate-cards"


def test_local_env_profile_is_snapshotted_write_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ORCH_LOCAL_MACHINE_ID", "studio/one")
    monkeypatch.setenv("ORCH_LOCAL_HOURLY_COST_USD", "12.5")
    monkeypatch.setenv("ORCH_LOCAL_ENERGY_COST_USD_PER_KWH", "0.18")
    monkeypatch.setenv("ORCH_LOCAL_GPU_HOURLY_COST_USD", "3.75")

    profile, version = load_local_cost_profile(tmp_path)

    assert version.startswith("local-studio-one-")
    path = _rate_dir(tmp_path) / f"{version}.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rate_card_version"] == version
    assert data["machine_id"] == "studio-one"
    assert data["hourly_cost_usd"] == 12.5
    assert data["energy_cost_usd_per_kwh"] == 0.18
    assert data["gpu_hourly_cost_usd"] == 3.75
    assert profile == data

    monkeypatch.setenv("ORCH_LOCAL_HOURLY_COST_USD", "99")
    next_profile, next_version = load_local_cost_profile(tmp_path)

    assert next_version == version
    assert next_profile["hourly_cost_usd"] == 12.5
    assert len(list(_rate_dir(tmp_path).glob("local-*.json"))) == 1


def test_existing_newest_local_snapshot_is_reused(tmp_path: Path) -> None:
    rate_dir = _rate_dir(tmp_path)
    rate_dir.mkdir(parents=True)
    (rate_dir / "local-rig-2026-04-22T10:00:00Z.json").write_text(
        json.dumps({
            "rate_card_version": "local-rig-2026-04-22T10:00:00Z",
            "hourly_cost_usd": 1.0,
        }),
        encoding="utf-8",
    )
    newest = rate_dir / "local-rig-2026-04-22T11:00:00Z.json"
    newest.write_text(
        json.dumps({
            "rate_card_version": "local-rig-2026-04-22T11:00:00Z",
            "hourly_cost_usd": 2.0,
        }),
        encoding="utf-8",
    )

    profile, version = load_local_cost_profile(tmp_path)

    assert version == "local-rig-2026-04-22T11:00:00Z"
    assert profile["hourly_cost_usd"] == 2.0
    assert len(list(rate_dir.glob("local-*.json"))) == 2


def test_projectless_profile_does_not_require_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("ORCH_LOCAL_MACHINE_ID", "offline")

    profile, version = load_local_cost_profile(None)

    assert version.startswith("local-offline-")
    assert profile["rate_card_version"] == version
    assert profile["machine_id"] == "offline"
