"""Durable workflow definitions for the orchestrator runtime."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

STEP_TYPES = ("phase", "gate", "checkpoint")
PHASE_HANDLERS = (
    "memory_refresh",
    "persona_forum",
    "architect",
    "architect_plan",
    "architect_refine",
    "micro_task_breakdown",
    "implementation",
    "testing",
    "guru_escalation",
    "review",
    "deployment",
)
GATE_HANDLERS = ("approve_plan_draft", "approve_sprint_plan", "approve_review")
CHECKPOINT_HANDLERS = ("operator_checkpoint",)
SUPPORTED_HANDLERS = PHASE_HANDLERS + GATE_HANDLERS + CHECKPOINT_HANDLERS

DEFAULT_WORKFLOW: list[dict[str, Any]] = [
    {
        "id": "memory_refresh",
        "title": "Palace Memory Refresh",
        "type": "phase",
        "handler": "memory_refresh",
        "enabled": True,
        "config": {},
    },
    {
        "id": "persona_forum",
        "title": "Founding Team Forum",
        "type": "phase",
        "handler": "persona_forum",
        "enabled": True,
        "config": {
            "auto_generate": True,
            "personas": [],
        },
    },
    {
        "id": "architect_plan",
        "title": "Architect — Plan (pass 1)",
        "type": "phase",
        "handler": "architect_plan",
        "enabled": True,
    },
    {
        "id": "approve_plan_draft",
        "title": "Approve Plan Draft",
        "type": "gate",
        "handler": "approve_plan_draft",
        "enabled": True,
    },
    {
        "id": "architect_refine",
        "title": "Architect — Refine",
        "type": "phase",
        "handler": "architect_refine",
        "enabled": True,
    },
    {
        "id": "approve_sprint_plan",
        "title": "Approve Sprint Plan",
        "type": "gate",
        "handler": "approve_sprint_plan",
        "enabled": True,
    },
    {
        "id": "micro_task_breakdown",
        "title": "Micro Task Breakdown",
        "type": "phase",
        "handler": "micro_task_breakdown",
        "enabled": True,
    },
    {
        "id": "implementation",
        "title": "Implementation",
        "type": "phase",
        "handler": "implementation",
        "enabled": True,
    },
    {
        "id": "testing",
        "title": "Testing",
        "type": "phase",
        "handler": "testing",
        "enabled": True,
    },
    {
        "id": "guru_escalation",
        "title": "Escalated Resolution Council",
        "type": "phase",
        "handler": "guru_escalation",
        "enabled": False,
    },
    {
        "id": "review",
        "title": "Review",
        "type": "phase",
        "handler": "review",
        "enabled": True,
    },
    {
        "id": "approve_review",
        "title": "Approve Review",
        "type": "gate",
        "handler": "approve_review",
        "enabled": True,
    },
    {
        "id": "deployment",
        "title": "Deployment",
        "type": "phase",
        "handler": "deployment",
        "enabled": True,
    },
]


def workflow_path(project_dir: Path) -> Path:
    path = project_dir / ".orchestrator" / "control" / "workflow.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_step(raw: dict[str, Any]) -> dict[str, Any]:
    step_id = str(raw.get("id", "")).strip()
    title = str(raw.get("title", step_id)).strip() or step_id
    step_type = str(raw.get("type", "")).strip()
    handler = str(raw.get("handler", step_id)).strip()
    enabled = bool(raw.get("enabled", True))
    description = str(raw.get("description", "")).strip()
    config = raw.get("config")
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError(f"Workflow step '{step_id}' config must be an object")

    if not step_id:
        raise ValueError("Workflow steps must have a non-empty id")
    if step_type not in STEP_TYPES:
        allowed = ", ".join(STEP_TYPES)
        raise ValueError(f"Workflow step '{step_id}' has invalid type '{step_type}'. Expected one of: {allowed}")
    if handler not in SUPPORTED_HANDLERS:
        allowed = ", ".join(SUPPORTED_HANDLERS)
        raise ValueError(f"Workflow step '{step_id}' has unsupported handler '{handler}'. Expected one of: {allowed}")
    if step_type == "phase" and handler not in PHASE_HANDLERS:
        raise ValueError(f"Workflow step '{step_id}' must use a phase handler")
    if step_type == "gate" and handler not in GATE_HANDLERS:
        raise ValueError(f"Workflow step '{step_id}' must use a gate handler")
    if step_type == "checkpoint" and handler not in CHECKPOINT_HANDLERS:
        raise ValueError(f"Workflow step '{step_id}' must use a checkpoint handler")
    return {
        "id": step_id,
        "title": title,
        "type": step_type,
        "handler": handler,
        "enabled": enabled,
        "description": description,
        "config": config,
    }


def validate_workflow(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("Workflow must be a non-empty list of steps")
    normalized = [_normalize_step(step) for step in steps]
    ids = [step["id"] for step in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Workflow step ids must be unique")
    if "architect" not in ids and "architect_plan" not in ids:
        raise ValueError(
            "Workflow must include an 'architect' step (or the split "
            "'architect_plan' + 'architect_refine' pair)"
        )
    if "deployment" not in ids:
        raise ValueError("Workflow must include a 'deployment' step")
    return normalized


def default_workflow() -> list[dict[str, Any]]:
    return deepcopy(DEFAULT_WORKFLOW)


_H6_5_SPLIT_STEP_IDS = frozenset({
    "architect_plan",
    "approve_plan_draft",
    "architect_refine",
})


def _merge_missing_default_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert newly introduced default steps into legacy saved workflows."""
    merged = list(steps)
    ids = {step["id"] for step in merged}
    # H6.5 compat: if a legacy workflow still uses the combined 'architect'
    # step, don't splice in the new plan/approve/refine trio alongside it —
    # that would double-run the role. Operators opt into the split by
    # replacing 'architect' with the three new steps explicitly.
    legacy_architect_present = "architect" in ids
    for index, default_step in enumerate(default_workflow()):
        if default_step["id"] in ids:
            continue
        if legacy_architect_present and default_step["id"] in _H6_5_SPLIT_STEP_IDS:
            continue
        insert_at = len(merged)
        for later_default in DEFAULT_WORKFLOW[index + 1:]:
            for pos, existing in enumerate(merged):
                if existing["id"] == later_default["id"]:
                    insert_at = pos
                    break
            if insert_at != len(merged):
                break
        merged.insert(insert_at, default_step)
        ids.add(default_step["id"])
    return _move_preplanning_steps_to_front(merged)


def _move_preplanning_steps_to_front(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep memory and persona setup before any planning step after migration."""
    preplanning_ids = ("memory_refresh", "persona_forum")
    planning_ids = {"architect", "architect_plan"}
    first_planning = next(
        (index for index, step in enumerate(steps) if step["id"] in planning_ids),
        None,
    )
    if first_planning is None:
        return steps

    preplanning = [step for step in steps if step["id"] in preplanning_ids]
    if not preplanning:
        return steps
    remaining = [step for step in steps if step["id"] not in preplanning_ids]
    insert_at = next(
        (index for index, step in enumerate(remaining) if step["id"] in planning_ids),
        len(remaining),
    )
    ordered_preplanning = [
        step for wanted_id in preplanning_ids for step in preplanning if step["id"] == wanted_id
    ]
    return remaining[:insert_at] + ordered_preplanning + remaining[insert_at:]


def load_workflow(project_dir: Path) -> list[dict[str, Any]]:
    path = workflow_path(project_dir)
    if not path.exists():
        steps = default_workflow()
        save_workflow(project_dir, steps)
        return steps
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read workflow: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("Workflow file must contain a list")
    normalized = validate_workflow(data)
    merged = _merge_missing_default_steps(normalized)
    if merged != normalized:
        save_workflow(project_dir, merged)
    return merged


def save_workflow(project_dir: Path, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = validate_workflow(steps)
    path = workflow_path(project_dir)
    path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return normalized


def enabled_steps(project_dir: Path) -> list[dict[str, Any]]:
    return [step for step in load_workflow(project_dir) if step.get("enabled", True)]


def valid_start_steps(project_dir: Path) -> list[str]:
    return [step["id"] for step in enabled_steps(project_dir)]


def update_step_config(
    project_dir: Path,
    step_id: str,
    config_updates: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge config into one workflow step and persist the result."""
    steps = load_workflow(project_dir)
    updated = False
    for step in steps:
        if step["id"] != step_id:
            continue
        current = step.get("config") or {}
        if not isinstance(current, dict):
            current = {}
        step["config"] = {**current, **config_updates}
        updated = True
        break
    if not updated:
        raise ValueError(f"Workflow step '{step_id}' not found")
    return save_workflow(project_dir, steps)
