"""Durable operator controls for resumable orchestrator runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.lib.intents import consume_prompt_intents
from orchestrator.lib.memory_palace import wakeup_path

PHASES = (
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
GATES = ("approve_plan_draft", "approve_sprint_plan", "approve_review")
RUN_STEPS = (
    "memory_refresh",
    "persona_forum",
    "architect",
    "architect_plan",
    "approve_plan_draft",
    "architect_refine",
    "approve_sprint_plan",
    "micro_task_breakdown",
    "implementation",
    "testing",
    "guru_escalation",
    "review",
    "approve_review",
    "deployment",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_run_step(step: str) -> str:
    """Return a normalized run step or raise ValueError."""
    normalized = step.strip()
    if normalized not in RUN_STEPS:
        allowed = ", ".join(RUN_STEPS)
        raise ValueError(f"Unknown run step '{step}'. Expected one of: {allowed}")
    return normalized


def validate_phase(phase: str) -> str:
    """Return a normalized agent phase or raise ValueError."""
    normalized = phase.strip()
    if normalized not in PHASES:
        allowed = ", ".join(PHASES)
        raise ValueError(f"Unknown phase '{phase}'. Expected one of: {allowed}")
    return normalized


def control_dir(project_dir: Path) -> Path:
    path = project_dir / ".orchestrator" / "control"
    path.mkdir(parents=True, exist_ok=True)
    return path


def instructions_path(project_dir: Path) -> Path:
    return control_dir(project_dir) / "instructions.jsonl"


def compact_context_path(project_dir: Path) -> Path:
    return control_dir(project_dir) / "context.compact.md"


def append_instruction(
    project_dir: Path,
    instruction: str,
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    """Append a durable user instruction for all phases or one phase."""
    clean_instruction = instruction.strip()
    if not clean_instruction:
        raise ValueError("Instruction cannot be empty")
    clean_phase = validate_phase(phase) if phase else None
    entry = {
        "ts": now_iso(),
        "phase": clean_phase,
        "instruction": clean_instruction,
    }
    path = instructions_path(project_dir)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_instructions(
    project_dir: Path,
    *,
    phase: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read recent instructions relevant to a phase."""
    path = instructions_path(project_dir)
    if not path.exists():
        return []
    clean_phase = validate_phase(phase) if phase else None
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        item_phase = item.get("phase")
        if clean_phase is not None and item_phase not in (None, clean_phase):
            continue
        instruction = item.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            continue
        entries.append(item)
    return entries[-limit:]


def _read_text_if_exists(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _manifest_summary(project_dir: Path) -> list[str]:
    """Summarize the dominant framework/manifests for prompt compaction."""
    lines: list[str] = []

    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        scripts = sorted((data.get("scripts") or {}).keys()) if isinstance(data, dict) else []
        package_manager = data.get("packageManager") if isinstance(data, dict) else None
        lines.append("- npm/js project detected via package.json")
        if isinstance(package_manager, str) and package_manager:
            lines.append(f"- package manager: {package_manager}")
        if scripts:
            lines.append(f"- scripts: {', '.join(scripts[:10])}")

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        lines.append("- Python project detected via pyproject.toml")
    if (project_dir / "uv.lock").exists():
        lines.append("- uv-managed environment present (uv.lock)")
    if (project_dir / "requirements.txt").exists():
        lines.append("- Python dependencies also declared in requirements.txt")
    if (project_dir / "Pipfile").exists():
        lines.append("- Pipenv metadata present (Pipfile)")

    dotnet_markers = list(project_dir.glob("*.sln")) + list(project_dir.glob("*.csproj"))
    if dotnet_markers:
        lines.append("- .NET project detected via solution/project files")
        lines.extend(f"- manifest: {path.name}" for path in dotnet_markers[:6])
    if (project_dir / "global.json").exists():
        lines.append("- global.json present for dotnet sdk pinning")

    if not lines:
        lines.append("- No common framework manifest detected; inspect repo-local docs and scripts.")
    return lines


def build_operator_context(
    project_dir: Path,
    phase: str,
    *,
    max_chars: int = 12000,
) -> str:
    """Build prompt context from compact state plus injected instructions."""
    clean_phase = validate_phase(phase)
    sections: list[str] = []

    compact = _read_text_if_exists(compact_context_path(project_dir), max_chars)
    if compact.strip():
        sections.append("## Compact Project Context\n\n" + compact.strip())

    wakeup = _read_text_if_exists(wakeup_path(project_dir), max_chars // 2)
    if wakeup.strip():
        sections.append("## Palace Wake-Up\n\n" + wakeup.strip())

    instructions = read_instructions(project_dir, phase=clean_phase, limit=20)
    if instructions:
        lines = ["## User Instructions"]
        for item in instructions:
            scope = item.get("phase") or "all phases"
            lines.append(f"- [{scope}] {item['instruction']}")
        sections.append("\n".join(lines))

    context = "\n\n".join(sections).strip()
    if len(context) > max_chars:
        context = context[-max_chars:]
    return context


def append_operator_context(
    project_dir: Path,
    phase: str,
    prompt: str,
    *,
    events: Any | None = None,
) -> str:
    """Append durable operator context to a prompt if present."""
    clean_phase = validate_phase(phase)
    intent_lines: list[str] = []
    applied_events: list[dict[str, Any]] = []
    if events is not None:
        intent_lines, applied_events = consume_prompt_intents(project_dir, clean_phase)
    context = build_operator_context(project_dir, clean_phase)
    if intent_lines:
        context = (
            f"{context.rstrip()}\n\n" if context else ""
        ) + "## Operator Intent\n" + "\n".join(intent_lines)
    if events is not None and hasattr(events, "emit"):
        for event in applied_events:
            events.emit("operator_intent_applied", project_id=project_dir.name, **event)
    if not context:
        return prompt
    return (
        f"{prompt.rstrip()}\n\n"
        "Additional operator context for this run:\n\n"
        f"{context}\n"
    )


def write_compact_context(project_dir: Path, *, max_chars: int = 18000) -> dict[str, Any]:
    """Create a deterministic compact context file from project artifacts.

    This intentionally avoids another LLM call. It gives small-context models
    a bounded project packet made from the durable files the framework already
    owns, plus recent agent log headlines.
    """
    path = compact_context_path(project_dir)
    sections = [
        "# Compact Project Context",
        "",
        f"Generated: {now_iso()}",
        "",
    ]

    sections.extend([
        "## Framework Summary",
        "",
        *_manifest_summary(project_dir),
        "",
    ])

    artifact_budget = max(3000, max_chars // 4)
    for name in (
        "qwendea.md",
        "PERSONA_FORUM.md",
        "FOUNDING_TEAM.json",
        ".orchestrator/memory/wake-up.md",
        "PRD.md",
        "prd.md",
        "project-context.md",
        "PROJECT_CONTEXT.md",
        "README.md",
        "sprint-plan.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "DEPLOY.md",
    ):
        file_path = project_dir / name
        if not file_path.exists():
            continue
        text = _read_text_if_exists(file_path, artifact_budget).strip()
        if not text:
            continue
        sections.extend([f"## {name}", "", text, ""])

    logs_dir = project_dir / ".orchestrator" / "logs"
    if logs_dir.exists():
        sections.extend(["## Recent Agent Log Events", ""])
        for log_path in sorted(logs_dir.glob("*.jsonl")):
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for raw in lines[-5:]:
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event = item.get("event") or item.get("message") or "event"
                message = item.get("message") or ""
                sections.append(f"- {log_path.stem}: {event} - {message}")
        sections.append("")

    instructions = read_instructions(project_dir, limit=12)
    if instructions:
        sections.extend(["## Persistent Operator Notes", ""])
        for item in instructions:
            scope = item.get("phase") or "all phases"
            sections.append(f"- [{scope}] {item['instruction']}")
        sections.append("")

    content = "\n".join(sections).strip() + "\n"
    if len(content) > max_chars:
        content = content[: max_chars - 80].rstrip() + "\n\n[compact context truncated]\n"
    path.write_text(content, encoding="utf-8")
    return {
        "path": str(path.relative_to(project_dir)),
        "bytes": path.stat().st_size,
        "max_chars": max_chars,
    }
