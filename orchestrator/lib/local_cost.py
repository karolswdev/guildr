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


def rate_card_snapshot_ref(rate_card_version: str) -> str:
    """Return the replay-safe repo-relative path for a rate-card version."""
    return f".orchestrator/costs/rate-cards/{rate_card_version}.json"


def annotate_rate_card_snapshot_status(
    project_dir: Path | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Mark whether a usage payload's referenced rate-card snapshot exists.

    Replay must not silently substitute current prices when a historical
    snapshot is missing. For estimated costs, a missing referenced card makes
    the affected row unknown so downstream folds show it as untrusted.
    """
    cost = payload.get("cost")
    if not isinstance(cost, dict):
        cost = {}
        payload["cost"] = cost

    version = _string(cost.get("rate_card_version")) or _string(payload.get("rate_card_version"))
    if not version:
        return payload
    cost["rate_card_version"] = version
    payload["rate_card_version"] = version

    ref = _string(cost.get("rate_card_ref")) or _string(payload.get("rate_card_ref"))
    if not ref:
        ref = rate_card_snapshot_ref(version)
    cost["rate_card_ref"] = ref
    payload["rate_card_ref"] = ref

    exists = _rate_card_ref_exists(project_dir, ref)
    checked = exists is not None
    missing = exists is False
    cost["rate_card_checked"] = checked
    cost["rate_card_missing"] = missing
    payload["rate_card_checked"] = checked
    payload["rate_card_missing"] = missing
    if missing:
        _mark_missing_rate_card(payload, cost)
    return payload


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
    path = project_dir / rate_card_snapshot_ref(version)
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


def _rate_card_ref_exists(project_dir: Path | None, ref: str) -> bool | None:
    if project_dir is None:
        return None
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts:
        return False
    if path.parts[:3] != (".orchestrator", "costs", "rate-cards"):
        return False
    return (project_dir / path).is_file()


def _mark_missing_rate_card(payload: dict[str, Any], cost: dict[str, Any]) -> None:
    if cost.get("source") == "provider_reported" or payload.get("source") == "provider_reported":
        return
    payload["source"] = "unknown"
    payload["confidence"] = "none"
    payload["cost_usd"] = None
    cost["source"] = "unknown"
    cost["confidence"] = "none"
    cost["effective_cost"] = None
    cost["estimated_cost"] = None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


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
