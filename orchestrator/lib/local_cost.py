"""Versioned local cost profile for llama.cpp / local inference estimates."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROFILE: dict[str, Any] = {
    "machine_id": "local",
    "hourly_cost_usd": 0.0,
    "energy_cost_usd_per_kwh": 0.0,
    "gpu_hourly_cost_usd": 0.0,
    "default_source": "local_estimate",
}


def load_local_cost_profile(project_dir: Path | None = None) -> tuple[dict[str, Any], str]:
    """Return (profile, rate_card_version) for local llama.cpp estimates.

    Resolution order:
    1. Newest `.orchestrator/costs/rate-cards/local-*.json` under project_dir.
    2. Built-in default with version `local-default-<bootstrap-ts>`.

    Versioning is write-once: this persists a snapshot file the first time a
    machine profile is observed; replay later resolves the original version
    rather than recomputing from current machine config.
    """
    if project_dir is not None:
        rate_dir = project_dir / ".orchestrator" / "costs" / "rate-cards"
        if rate_dir.is_dir():
            candidates = sorted(rate_dir.glob("local-*.json"))
            if candidates:
                path = candidates[-1]
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        version = str(data.get("rate_card_version") or path.stem)
                        return data, version
                except (OSError, json.JSONDecodeError):
                    pass

    profile, version = _default_profile()
    if project_dir is not None:
        profile = _persist_snapshot(project_dir, profile, version)
        version = str(profile.get("rate_card_version") or version)
    return profile, version


def _default_profile() -> tuple[dict[str, Any], str]:
    machine = _safe_machine_id(
        os.environ.get("ORCH_LOCAL_MACHINE_ID", DEFAULT_PROFILE["machine_id"])
    )
    snapshot_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    version = f"local-{machine}-{snapshot_ts}"
    profile = {
        **DEFAULT_PROFILE,
        "machine_id": machine,
        "hourly_cost_usd": _env_float(
            "ORCH_LOCAL_HOURLY_COST_USD",
            DEFAULT_PROFILE["hourly_cost_usd"],
        ),
        "energy_cost_usd_per_kwh": _env_float(
            "ORCH_LOCAL_ENERGY_COST_USD_PER_KWH",
            DEFAULT_PROFILE["energy_cost_usd_per_kwh"],
        ),
        "gpu_hourly_cost_usd": _env_float(
            "ORCH_LOCAL_GPU_HOURLY_COST_USD",
            DEFAULT_PROFILE["gpu_hourly_cost_usd"],
        ),
        "rate_card_version": version,
        "provider_kind": "local",
        "snapshot_source": "env_or_default",
        "snapshot_created_at": snapshot_ts,
    }
    return profile, version


def _persist_snapshot(project_dir: Path, profile: dict[str, Any], version: str) -> dict[str, Any]:
    rate_dir = project_dir / ".orchestrator" / "costs" / "rate-cards"
    rate_dir.mkdir(parents=True, exist_ok=True)
    path = rate_dir / f"{version}.json"
    payload = dict(profile)
    try:
        with path.open("x", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except FileExistsError:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return payload


def _safe_machine_id(raw: object) -> str:
    value = str(raw or DEFAULT_PROFILE["machine_id"])
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)
    return safe.strip("-_.") or str(DEFAULT_PROFILE["machine_id"])


def _env_float(name: str, default: Any) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def estimate_local_cost(
    profile: dict[str, Any],
    *,
    wall_ms: float,
    estimated_energy_wh: float | None = None,
    gpu_seconds: float | None = None,
) -> float:
    """Compute local effective cost from the documented formula."""
    hourly = float(profile.get("hourly_cost_usd") or 0.0)
    energy = float(profile.get("energy_cost_usd_per_kwh") or 0.0)
    gpu_hourly = float(profile.get("gpu_hourly_cost_usd") or 0.0)

    compute_cost = hourly * (wall_ms / 3_600_000.0)
    energy_cost = energy * ((estimated_energy_wh or 0.0) / 1000.0)
    gpu_cost = gpu_hourly * ((gpu_seconds or 0.0) / 3600.0)
    return compute_cost + energy_cost + gpu_cost
