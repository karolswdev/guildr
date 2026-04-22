"""Per-phase loop-event ref resolution (H6.5+).

Loop events carry three ref lists — ``artifact_refs`` (what the phase
produces), ``memory_refs`` (what the phase read in), and
``evidence_refs`` (task ids / verification anchors) — that the PWA
snapshot engine accumulates into ``loops.byAtom[atomId]``. Until this
helper existed every emitter passed empty lists, leaving the frontend
with no way to render a task → test → review chain.

Resolution rules:
- Only paths that actually exist on disk are returned. A ref is a
  promise that a real artifact is there — consumers should be able to
  follow the ref without defending against missing files.
- When ``include_outputs=False`` (emitted on ``loop_entered`` or on an
  exception before the phase produced anything), output artifacts are
  omitted. Memory refs and task evidence still come along.
- Task evidence expands to ``task-<id>`` strings parsed out of
  ``sprint-plan.md``; ``implementation`` additionally contributes any
  task-declared file that's already on disk.
"""

from __future__ import annotations

from typing import Any

from orchestrator.lib.state import State


_PHASE_PROFILES: dict[str, dict[str, list[str]]] = {
    "memory_refresh": {
        "outputs": [".orchestrator/memory/wake-up.md"],
        "memory": [],
    },
    "persona_forum": {
        "outputs": ["PERSONA_FORUM.md"],
        "memory": [".orchestrator/memory/wake-up.md"],
    },
    "architect": {
        "outputs": ["sprint-plan.md"],
        "memory": [
            ".orchestrator/memory/wake-up.md",
            ".orchestrator/context.compact.md",
            "PERSONA_FORUM.md",
        ],
    },
    "architect_plan": {
        "outputs": [
            "sprint-plan.md",
            ".orchestrator/drafts/architect-pass-1.md",
            ".orchestrator/drafts/architect-plan-status.json",
        ],
        "memory": [
            ".orchestrator/memory/wake-up.md",
            ".orchestrator/context.compact.md",
            "PERSONA_FORUM.md",
        ],
    },
    "architect_refine": {
        "outputs": ["sprint-plan.md", ".orchestrator/escalation.md"],
        "memory": [
            ".orchestrator/memory/wake-up.md",
            ".orchestrator/context.compact.md",
            "PERSONA_FORUM.md",
            ".orchestrator/drafts/architect-plan-status.json",
        ],
    },
    "micro_task_breakdown": {
        "outputs": ["sprint-plan.md"],
        "memory": [],
    },
    "implementation": {
        "outputs": [],
        "memory": ["sprint-plan.md"],
    },
    "testing": {
        "outputs": ["TEST_REPORT.md"],
        "memory": ["sprint-plan.md"],
    },
    "guru_escalation": {
        "outputs": [".orchestrator/escalation.md"],
        "memory": ["TEST_REPORT.md", "sprint-plan.md"],
    },
    "review": {
        "outputs": ["REVIEW.md"],
        "memory": ["sprint-plan.md", "TEST_REPORT.md"],
    },
    "deployment": {
        "outputs": ["DEPLOY.md"],
        "memory": ["REVIEW.md"],
    },
}


def refs_for_phase(
    name: str, state: State, *, include_outputs: bool = True
) -> dict[str, list[str]]:
    """Return ``{artifact_refs, evidence_refs, memory_refs}`` for a phase.

    Paths are project-dir relative strings, filtered to ones that
    exist on disk right now. Task evidence is expanded from
    ``sprint-plan.md`` when relevant.
    """
    profile = _PHASE_PROFILES.get(name, {})
    project = state.project_dir

    memory_refs = [r for r in profile.get("memory", []) if (project / r).exists()]

    artifact_refs: list[str] = []
    if include_outputs:
        artifact_refs.extend(
            r for r in profile.get("outputs", []) if (project / r).exists()
        )

    evidence_refs: list[str] = []
    if name in ("implementation", "testing", "review"):
        evidence_refs, extra_artifacts = _task_refs(
            project, include_files=(name == "implementation")
        )
        artifact_refs.extend(extra_artifacts)

    # De-dupe while preserving order — callers merge these into sets
    # downstream anyway, but keeping them tidy makes logs readable.
    return {
        "artifact_refs": _dedupe(artifact_refs),
        "evidence_refs": _dedupe(evidence_refs),
        "memory_refs": _dedupe(memory_refs),
    }


def _task_refs(project: Any, *, include_files: bool) -> tuple[list[str], list[str]]:
    plan_path = project / "sprint-plan.md"
    if not plan_path.exists():
        return [], []
    try:
        from orchestrator.lib.sprint_plan import parse_tasks

        tasks = parse_tasks(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return [], []

    evidence: list[str] = []
    files: list[str] = []
    for task in tasks:
        evidence.append(f"task-{task.id}")
        if include_files:
            for f in task.files:
                if (project / f).exists():
                    files.append(f)
    return evidence, files


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
