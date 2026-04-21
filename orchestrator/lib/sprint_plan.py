"""Sprint plan parsing, slicing, and evidence patch helpers.

All roles use these helpers to work with sprint-plan.md sections
without loading the entire file into context.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_TASK_RE = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)


@dataclass
class Task:
    """A single task parsed from a sprint plan."""

    id: int
    name: str
    deps: list[str]
    body: str
    priority: str = ""
    files: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)
    evidence_log: list[dict[str, Any]] = field(default_factory=list)


def parse_tasks(sprint_plan_md: str) -> list[Task]:
    """Parse all tasks from a sprint-plan.md string.

    Returns tasks in document order with id, name, deps, and full body.
    """
    tasks: list[Task] = []
    matches = list(_TASK_RE.finditer(sprint_plan_md))

    for i, match in enumerate(matches):
        task_id = int(match.group(1))
        task_name = match.group(2).strip()
        start = match.start()

        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            risks_match = re.search(r"^## Risks", sprint_plan_md, re.MULTILINE)
            if risks_match:
                end = risks_match.start()
            else:
                end = len(sprint_plan_md)

        body = sprint_plan_md[start:end].rstrip()
        tasks.append(Task(
            id=task_id,
            name=task_name,
            deps=_parse_deps(body),
            body=body,
            priority=_parse_priority(body),
            files=_parse_files(body),
            acceptance_criteria=_parse_acceptance_criteria(body),
            evidence_required=_parse_evidence_required(body),
            evidence_log=_parse_evidence_log(body),
        ))

    return tasks


def _parse_deps(body: str) -> list[str]:
    """Extract dependency list from a task body."""
    m = re.search(r"- \*\*Dependencies\*\*: (.+)$", body, re.MULTILINE)
    if not m:
        return []
    val = m.group(1).strip()
    if val.lower() == "none":
        return []
    return [d.strip() for d in val.split(",")]


def _parse_priority(body: str) -> str:
    """Extract priority from a task body."""
    m = re.search(r"- \*\*Priority\*\*: (P\d)", body, re.MULTILINE)
    return m.group(1) if m else ""


def _parse_files(body: str) -> list[str]:
    """Extract file list from a task body."""
    m = re.search(r"- \*\*Files\*\*: (.+)$", body, re.MULTILINE)
    if not m:
        return []
    val = m.group(1).strip()
    files = []
    for part in val.split(","):
        part = part.strip().strip("`").strip()
        if part:
            files.append(part)
    return files


def _parse_acceptance_criteria(body: str) -> list[str]:
    """Extract acceptance criteria from a task body."""
    m = re.search(
        r"\*\*Acceptance Criteria:\*\*\n(.*?)(?=\*\*Evidence Required:|\*\*Evidence Log:|\*\*Implementation Notes:|\Z)",
        body,
        re.DOTALL,
    )
    if not m:
        return []
    lines = []
    for line in m.group(1).strip().split("\n"):
        line = line.strip()
        if line.startswith("- ["):
            lines.append(line)
    return lines


def _parse_evidence_required(body: str) -> list[str]:
    """Extract evidence required items from a task body."""
    m = re.search(
        r"\*\*Evidence Required:\*\*\n(.*?)(?=\*\*Evidence Log:|\*\*Implementation Notes:|\Z)",
        body,
        re.DOTALL,
    )
    if not m:
        return []
    lines = []
    for line in m.group(1).strip().split("\n"):
        line = line.strip()
        if line.startswith("- "):
            lines.append(line.lstrip("- ").strip())
    return lines


def _parse_evidence_log(body: str) -> list[dict[str, Any]]:
    """Extract evidence log entries from a task body."""
    m = re.search(
        r"\*\*Evidence Log:\*\*(.*?)(?=\*\*Implementation Notes:|\Z)",
        body,
        re.DOTALL,
    )
    if not m:
        return []
    log_section = m.group(1)
    entries = []
    for line in log_section.split("\n"):
        line = line.strip()
        if line.startswith("- [x]") or line.startswith("- [ ]"):
            checked = line.startswith("- [x]")
            check_text = re.sub(r"^- \[[x ]\]\s*", "", line).strip()
            entries.append({
                "check": check_text,
                "passed": checked,
            })
    return entries


def slice_task(sprint_plan_md: str, task_id: int) -> str:
    """Return the task's section plus the sprint preamble.

    This keeps context-bounds small by only including:
    - The pre-task sprint memory/traceability sections
    - The specific task's full section
    """
    tasks = parse_tasks(sprint_plan_md)
    target = None
    for t in tasks:
        if t.id == task_id:
            target = t
            break

    if target is None:
        raise ValueError(f"Task {task_id} not found in sprint plan")

    preamble_match = re.search(
        r"(## Overview\n.*?)(?=\n## Tasks|\n## Risks|\Z)",
        sprint_plan_md,
        re.DOTALL,
    )
    preamble = preamble_match.group(1).strip() if preamble_match else "## Overview\n(no sprint memory recorded)\n"

    return f"{preamble}\n\n{target.body}"


def apply_evidence_patch(sprint_plan_md: str, patch: dict) -> str:
    """Apply an evidence patch to sprint-plan.md deterministically.

    The patch format:
    {
      "task_id": <N>,
      "entries": [
        {"check": "<what was checked>", "output": "...", "passed": true},
        ...
      ]
    }

    This replaces the Evidence Log section of the target task with
    checked checkboxes and recorded outputs.
    """
    task_id = patch["task_id"]
    entries = patch["entries"]

    tasks = parse_tasks(sprint_plan_md)
    target = None
    for t in tasks:
        if t.id == task_id:
            target = t
            break

    if target is None:
        raise ValueError(f"Task {task_id} not found in sprint plan")

    log_lines = ["**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)"]
    for entry in entries:
        check = entry.get("check", "")
        output = entry.get("output", "")
        passed = entry.get("passed", False)
        marker = "[x]" if passed else "[ ]"
        line = f"- {marker} {check}"
        if output:
            line += f", output recorded: ```{output}```"
        log_lines.append(line)

    new_log = "\n".join(log_lines)

    log_pattern = re.compile(
        r"(\*\*Evidence Log:\*\*)(.*?)(?=\*\*Implementation Notes:|\Z)",
        re.DOTALL,
    )

    def _replace_log(m: re.Match) -> str:
        original = m.group(0)
        trailing = original[len(original.rstrip()):]
        return new_log + trailing

    new_body = log_pattern.sub(_replace_log, target.body, count=1)

    tasks = parse_tasks(sprint_plan_md)
    current_target = None
    for t in tasks:
        if t.id == task_id:
            current_target = t
            break

    if current_target is None:
        full_plan = sprint_plan_md.replace(target.body, new_body, 1)
        return full_plan

    if current_target.body == target.body:
        full_plan = sprint_plan_md.replace(target.body, new_body, 1)
    else:
        tasks = parse_tasks(sprint_plan_md)
        for t in tasks:
            if t.id == task_id:
                current_body = t.body
                break
        else:
            raise ValueError(f"Task {task_id} not found in sprint plan after re-parse")
        full_plan = sprint_plan_md.replace(current_body, new_body, 1)

    return full_plan
