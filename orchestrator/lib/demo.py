"""Demo ceremony planning for visually demoable mini-sprint tasks (A-10).

First slice: detect demoable tasks from acceptance/evidence text, select an
adapter plan (starting with ``playwright_web``), and emit ``demo_planned`` or
``demo_skipped`` events stamped with memory provenance. Browser capture is
intentionally out of scope here — see ``docs/demo-ceremony-and-replay-evidence.md``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from orchestrator.lib.memory_palace import memory_event_fields
from orchestrator.lib.scrub import scrub_text

ADAPTER_PLAYWRIGHT: str = "playwright_web"

CONFIDENCE_EXPLICIT: str = "explicit_playwright"
CONFIDENCE_OPERATOR: str = "operator_requested"
CONFIDENCE_INFERRED: str = "inferred_interactive_web"
CONFIDENCE_STATIC: str = "static_visual"
CONFIDENCE_NONE: str = "not_demoable"

CONFIDENCES: frozenset[str] = frozenset({
    CONFIDENCE_EXPLICIT,
    CONFIDENCE_OPERATOR,
    CONFIDENCE_INFERRED,
    CONFIDENCE_STATIC,
    CONFIDENCE_NONE,
})

_EXPLICIT_KEYWORDS: tuple[str, ...] = (
    "playwright",
    "demo.gif",
    "interaction.webm",
    "demo spec",
    "browser test",
    "route check",
    "video capture",
    "gif capture",
)
_INFERRED_KEYWORDS: tuple[str, ...] = (
    "ui",
    "page",
    "route",
    "app",
    "canvas",
    "form",
    "game",
    "map",
    "dashboard",
    "visual state",
    "mobile viewport",
    "pwa",
    "story lens",
    "object lens",
    "scene",
    "sheet",
    "overlay",
)
_STATIC_KEYWORDS: tuple[str, ...] = (
    "static page",
    "static html",
    "static visual",
    "screenshot",
)

_FRONTEND_PATH_HINTS: tuple[str, ...] = (
    "web/frontend/",
    ".tsx",
    ".jsx",
    ".svelte",
    ".vue",
    "public/",
)


class DemoPlanError(ValueError):
    """Raised when a demo plan cannot be safely emitted."""


def detect_playwright_demo_plan(
    *,
    acceptance_text: str = "",
    evidence_text: str = "",
    operator_requested: bool = False,
    repo_has_playwright: bool = False,
    changed_files: list[str] | None = None,
    start_command: str | None = None,
    test_command: str | None = None,
    spec_path: str | None = None,
    route: str | None = None,
    viewports: list[str] | None = None,
    capture_policy: list[str] | None = None,
) -> dict[str, Any]:
    """Return a ``playwright_web`` adapter plan for a candidate task.

    Conservative: returns ``CONFIDENCE_NONE`` with a source-backed reason when
    no useful signal is present. Never launches a browser; the plan is text-only
    metadata the ceremony flow will act on later.
    """
    combined = f"{acceptance_text}\n{evidence_text}".lower()
    files = [str(item).lower() for item in (changed_files or []) if isinstance(item, str) and item.strip()]
    frontend_touched = any(
        any(hint in path for hint in _FRONTEND_PATH_HINTS) for path in files
    )

    explicit_hit = any(keyword in combined for keyword in _EXPLICIT_KEYWORDS)
    inferred_hit = any(keyword in combined for keyword in _INFERRED_KEYWORDS)
    static_hit = any(keyword in combined for keyword in _STATIC_KEYWORDS)

    if explicit_hit:
        confidence = CONFIDENCE_EXPLICIT
        reason = "acceptance or evidence text explicitly requested a Playwright-backed demo"
    elif operator_requested:
        confidence = CONFIDENCE_OPERATOR
        reason = "operator intent requested an interactive web demo"
    elif inferred_hit and (repo_has_playwright or frontend_touched):
        confidence = CONFIDENCE_INFERRED
        reason = "frontend surface with a runnable route is inferred from the task"
    elif static_hit:
        confidence = CONFIDENCE_STATIC
        reason = "only static visual proof is currently supported for this task"
    else:
        confidence = CONFIDENCE_NONE
        reason = "no runnable visual surface detected in acceptance or evidence"

    plan: dict[str, Any] = {
        "adapter": ADAPTER_PLAYWRIGHT,
        "confidence": confidence,
        "reason": scrub_text(reason),
        "start_command": scrub_text(start_command or ""),
        "test_command": scrub_text(test_command or ""),
        "spec_path": scrub_text(spec_path or ""),
        "route": scrub_text(route or ""),
        "viewports": [scrub_text(v) for v in (viewports or []) if isinstance(v, str) and v.strip()],
        "capture_policy": [
            scrub_text(item)
            for item in (capture_policy or ["gif", "webm", "trace", "screenshot"])
            if isinstance(item, str) and item.strip()
        ],
    }
    return plan


def emit_demo_plan(
    event_bus: Any,
    project_dir: Path,
    plan: dict[str, Any],
    *,
    trigger_event_id: str,
    task_id: str | None = None,
    atom_id: str | None = None,
    project_id: str | None = None,
    source_refs: list[str] | None = None,
    artifact_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Emit ``demo_planned`` or ``demo_skipped`` for the given plan.

    ``demo_id`` is a deterministic hash of (task_id or atom_id, adapter,
    spec_path, trigger_event_id) so repeated calls for the same trigger stamp
    the same id and are safely idempotent at the ledger layer.
    """
    if not isinstance(plan, dict):
        raise DemoPlanError("plan must be a dict")
    adapter = _string(plan.get("adapter"))
    if not adapter:
        raise DemoPlanError("plan.adapter is required")
    confidence = _string(plan.get("confidence"))
    if confidence not in CONFIDENCES:
        raise DemoPlanError(f"unknown confidence: {confidence!r}")
    if not _string(trigger_event_id):
        raise DemoPlanError("trigger_event_id is required")

    subject = _string(task_id) or _string(atom_id) or "task"
    seed = f"{subject}|{adapter}|{_string(plan.get('spec_path'))}|{trigger_event_id}"
    demo_id = f"demo_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    refs = list(source_refs or [])
    if not any(ref == f"event:{trigger_event_id}" for ref in refs):
        refs.append(f"event:{trigger_event_id}")
    refs = _dedupe(refs)

    provenance = memory_event_fields(project_id, project_dir)

    common = {
        "project_id": project_id or project_dir.name,
        "demo_id": demo_id,
        "task_id": _string(task_id) or None,
        "atom_id": _string(atom_id) or None,
        "adapter": adapter,
        "confidence": confidence,
        "reason": _string(plan.get("reason")),
        "start_command": _string(plan.get("start_command")),
        "test_command": _string(plan.get("test_command")),
        "spec_path": _string(plan.get("spec_path")),
        "route": _string(plan.get("route")),
        "viewports": list(plan.get("viewports") or []),
        "capture_policy": list(plan.get("capture_policy") or []),
        "source_refs": refs,
        "artifact_refs": list(artifact_refs or []),
        "wake_up_hash": provenance["wake_up_hash"],
        "memory_refs": list(provenance["memory_refs"]),
        "plan": plan,
    }
    event_type = "demo_skipped" if confidence == CONFIDENCE_NONE else "demo_planned"
    return event_bus.emit(event_type, **common)


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
