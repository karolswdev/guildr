"""Optional MemPalace integration for project memory packets."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from orchestrator.lib.scrub import scrub_text

ROLE_WING_ROLES: tuple[str, ...] = (
    "architect",
    "coder",
    "tester",
    "reviewer",
    "narrator",
    "deployer",
    "judge",
)

PHASE_ROLE_WINGS: dict[str, str] = {
    "architect": "architect",
    "architect_plan": "architect",
    "architect_refine": "architect",
    "micro_task_breakdown": "architect",
    "implementation": "coder",
    "testing": "tester",
    "review": "reviewer",
    "deployment": "deployer",
    "narrator": "narrator",
}

MEMORY_COST_ACCOUNTING: dict[str, Any] = {
    "provider_kind": "external_cli",
    "usage_recorded": False,
    "reason": "MemPalace CLI calls do not expose token or cost usage to the orchestrator.",
}


def memory_dir(project_dir: Path) -> Path:
    path = project_dir / ".orchestrator" / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def wakeup_path(project_dir: Path) -> Path:
    return memory_dir(project_dir) / "wake-up.md"


def status_path(project_dir: Path) -> Path:
    return memory_dir(project_dir) / "status.txt"


def search_path(project_dir: Path) -> Path:
    return memory_dir(project_dir) / "last-search.txt"


def metadata_path(project_dir: Path) -> Path:
    return memory_dir(project_dir) / "metadata.json"


def wakeup_hash(project_dir: Path) -> str | None:
    path = wakeup_path(project_dir)
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def project_initialized(project_dir: Path) -> bool:
    return (project_dir / "mempalace.yaml").exists() or (project_dir / "entities.json").exists()


def project_wing(project_id: str | None, project_dir: Path) -> str:
    configured = os.environ.get("GUILDR_MEMPALACE_WING")
    if configured:
        return configured.strip()
    if project_id:
        return project_id
    meta = project_dir / ".orchestrator" / "project.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            maybe_id = data.get("id")
            if isinstance(maybe_id, str) and maybe_id.strip():
                return maybe_id.strip()
    return project_dir.name


def role_wing(project_id: str | None, project_dir: Path, role: str) -> str:
    """Return the deterministic MemPalace wing name reserved for one role."""
    clean_role = _slug(role)
    return f"{project_wing(project_id, project_dir)}.{clean_role}"


def role_wings(project_id: str | None, project_dir: Path) -> dict[str, str]:
    """Role-scoped wing contract, stubbed until live MCP/search is enabled."""
    return {role: role_wing(project_id, project_dir, role) for role in ROLE_WING_ROLES}


def role_wing_for_phase(project_id: str | None, project_dir: Path, phase: str) -> str | None:
    role = PHASE_ROLE_WINGS.get(phase)
    if role is None:
        return None
    return role_wing(project_id, project_dir, role)


def resolve_command() -> list[str] | None:
    configured = os.environ.get("GUILDR_MEMPALACE_CMD", "").strip()
    if configured:
        return shlex.split(configured)
    binary = shutil.which("mempalace")
    if binary:
        return [binary]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", "mempalace", "mempalace"]
    return None


def memory_status(project_id: str | None, project_dir: Path) -> dict[str, Any]:
    command = resolve_command()
    wakeup = wakeup_path(project_dir)
    status_file = status_path(project_dir)
    metadata = _read_json(metadata_path(project_dir))
    hash_value = wakeup_hash(project_dir)
    return {
        "project_id": project_id or project_dir.name,
        "available": command is not None,
        "command": " ".join(command) if command else None,
        "initialized": project_initialized(project_dir),
        "wing": project_wing(project_id, project_dir),
        "role_wings": _metadata_role_wings(metadata, project_id, project_dir),
        "cost_accounting": dict(MEMORY_COST_ACCOUNTING),
        "cached_wakeup": wakeup.read_text(encoding="utf-8") if wakeup.exists() else "",
        "cached_status": status_file.read_text(encoding="utf-8") if status_file.exists() else "",
        "last_search": search_path(project_dir).read_text(encoding="utf-8") if search_path(project_dir).exists() else "",
        "wake_up_hash": hash_value,
        "wake_up_bytes": wakeup.stat().st_size if wakeup.exists() else 0,
        "memory_refs": [".orchestrator/memory/wake-up.md"] if wakeup.exists() else [],
        "metadata": metadata,
    }


def memory_event_fields(project_id: str | None, project_dir: Path) -> dict[str, Any]:
    """Compact provenance fields to stamp on user-facing events (A-9)."""
    _ = project_id
    path = wakeup_path(project_dir)
    refs = [".orchestrator/memory/wake-up.md"] if path.exists() else []
    return {
        "wake_up_hash": wakeup_hash(project_dir),
        "memory_refs": refs,
    }


def memory_provenance(project_id: str | None, project_dir: Path) -> dict[str, Any]:
    """Return the compact memory packet other projections should cite."""
    status = memory_status(project_id, project_dir)
    return {
        "project_id": status["project_id"],
        "available": status["available"],
        "initialized": status["initialized"],
        "wing": status["wing"],
        "role_wings": status["role_wings"],
        "wake_up_hash": status["wake_up_hash"],
        "wake_up_bytes": status["wake_up_bytes"],
        "memory_refs": status["memory_refs"],
        "artifact_refs": status["memory_refs"],
        "cost_accounting": status["cost_accounting"],
    }


def sync_project_memory(project_id: str | None, project_dir: Path) -> dict[str, Any]:
    command = resolve_command()
    if command is None:
        raise RuntimeError("MemPalace is not available. Install it or configure GUILDR_MEMPALACE_CMD.")

    init_output = ""
    if not project_initialized(project_dir):
        init_output = _run(command, ["init", str(project_dir), "--yes"], cwd=project_dir)

    wing = project_wing(project_id, project_dir)
    mine_output = _run(command, ["mine", str(project_dir), "--wing", wing], cwd=project_dir)
    status_output = _run(command, ["status"], cwd=project_dir)
    wakeup_output = _run(command, ["wake-up", "--wing", wing], cwd=project_dir)

    status_path(project_dir).write_text(status_output, encoding="utf-8")
    wakeup_path(project_dir).write_text(wakeup_output, encoding="utf-8")
    metadata_path(project_dir).write_text(
        json.dumps(
            {
                "wing": wing,
                "role_wings": role_wings(project_id, project_dir),
                "cost_accounting": dict(MEMORY_COST_ACCOUNTING),
                "init_ran": bool(init_output),
                "command": command,
                "wake_up_hash": wakeup_hash(project_dir),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        **memory_status(project_id, project_dir),
        "init_output": init_output,
        "mine_output": mine_output,
        "wake_up": wakeup_output,
        "status_output": status_output,
    }


def refresh_wakeup(project_id: str | None, project_dir: Path) -> dict[str, Any]:
    command = resolve_command()
    if command is None:
        raise RuntimeError("MemPalace is not available. Install it or configure GUILDR_MEMPALACE_CMD.")
    wing = project_wing(project_id, project_dir)
    wakeup_output = _run(command, ["wake-up", "--wing", wing], cwd=project_dir)
    wakeup_path(project_dir).write_text(wakeup_output, encoding="utf-8")
    metadata = _read_json(metadata_path(project_dir))
    metadata["wing"] = wing
    metadata["role_wings"] = role_wings(project_id, project_dir)
    metadata["cost_accounting"] = dict(MEMORY_COST_ACCOUNTING)
    metadata["wake_up_hash"] = wakeup_hash(project_dir)
    metadata_path(project_dir).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {
        **memory_status(project_id, project_dir),
        "wake_up": wakeup_output,
    }


def search_memory(
    project_id: str | None,
    project_dir: Path,
    *,
    query: str,
    room: str | None = None,
    results: int = 5,
) -> dict[str, Any]:
    command = resolve_command()
    if command is None:
        raise RuntimeError("MemPalace is not available. Install it or configure GUILDR_MEMPALACE_CMD.")
    clean_query = scrub_text(query)
    clean_room = scrub_text(room) if room else None
    args = ["search", clean_query, "--wing", project_wing(project_id, project_dir), "--results", str(results)]
    if clean_room:
        args.extend(["--room", clean_room])
    output = _run(command, args, cwd=project_dir)
    clean_output = scrub_text(output)
    search_path(project_dir).write_text(clean_output, encoding="utf-8")
    return {
        **memory_status(project_id, project_dir),
        "query": clean_query,
        "room": clean_room,
        "results": results,
        "output": clean_output,
    }


def _run(command: list[str], args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        [*command, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"MemPalace command failed: {' '.join(args)}: {detail}")
    return completed.stdout.strip()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _metadata_role_wings(metadata: dict[str, Any], project_id: str | None, project_dir: Path) -> dict[str, str]:
    raw = metadata.get("role_wings")
    if isinstance(raw, dict):
        clean = {str(k): str(v) for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and k and v}
        if clean:
            return clean
    return role_wings(project_id, project_dir)


def _slug(value: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in value).strip("_") or "role"
