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

    Versioning is write-once: callers persist a snapshot file the first time a
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

    machine = os.environ.get("ORCH_LOCAL_MACHINE_ID", DEFAULT_PROFILE["machine_id"])
    snapshot_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    profile = {**DEFAULT_PROFILE, "machine_id": machine}
    return profile, f"local-{machine}-{snapshot_ts}"


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
