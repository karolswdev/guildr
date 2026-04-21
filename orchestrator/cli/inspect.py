"""Session inspection CLI for the orchestrator.

Usage:
    orchestrator inspect <project-id>                # list phases + status
    orchestrator inspect <project-id> --phase NAME   # dump phase session
    orchestrator inspect <project-id> --tokens       # show per-phase tokens
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def find_project(project_id: str) -> Path:
    """Resolve a project identifier to a project directory.

    Checks in order:
    1. Direct path existence
    2. ``.orchestrator-projects/<project_id>`` (default projects dir)
    3. ``/tmp/orchestrator-projects/<project_id>`` (legacy default)
    """
    # Direct path
    direct = Path(project_id)
    if direct.is_dir() and (direct / ".orchestrator" / "state.json").exists():
        return direct

    # Check common project directories
    for base in (
        Path.home() / ".orchestrator-projects",
        Path("/tmp/orchestrator-projects"),
        Path("."),
    ):
        candidate = base / project_id
        if candidate.is_dir() and (candidate / ".orchestrator" / "state.json").exists():
            return candidate

    raise FileNotFoundError(
        f"Project '{project_id}' not found. "
        "Checked: {project_id}, ~/.orchestrator-projects/{project_id}, "
        "/tmp/orchestrator-projects/{project_id}"
    )


def load_state(project_dir: Path) -> dict[str, Any]:
    """Load the orchestrator state.json."""
    state_file = project_dir / ".orchestrator" / "state.json"
    if not state_file.exists():
        print(f"Error: no state.json found in {project_dir / '.orchestrator'}",
              file=sys.stderr)
        sys.exit(1)
    return json.loads(state_file.read_text(encoding="utf-8"))


def list_phases(state: dict[str, Any], project_dir: Path) -> None:
    """List all phases with their status."""
    phases = [
        "architect",
        "implementation",
        "testing",
        "review",
        "deployment",
    ]

    # Map phase names to gate names
    phase_to_gate = {
        "architect": "approve_sprint_plan",
        "review": "approve_review",
    }

    current_phase = state.get("current_phase")
    retries = state.get("retries", {})
    gates = state.get("gates_approved", {})

    print(f"Project: {project_dir.name}")
    print(f"Current phase: {current_phase or 'none'}")
    print()
    print(f"{'Phase':<20} {'Retries':<10} {'Status':<20} {'Gate':<10}")
    print("-" * 60)

    for phase in phases:
        retry_count = retries.get(phase, 0)
        is_current = phase == current_phase
        status = "current" if is_current else ("done" if retry_count > 0 else "pending")

        # Check gate status using the phase-to-gate mapping
        gate_name = phase_to_gate.get(phase)
        if gate_name:
            gate_val = gates.get(gate_name)
            if gate_val is True:
                gate_str = "approved"
            elif gate_name in gates:
                gate_str = "rejected"
            else:
                gate_str = "-"
        else:
            gate_str = "-"

        prefix = ">>>" if is_current else "   "
        print(f"{prefix} {phase:<18} {retry_count:<10} {status:<20} {gate_str:<10}")

    # Show sessions if any
    sessions = state.get("sessions", {})
    if sessions:
        print()
        print("Sessions:")
        for phase, session_id in sessions.items():
            print(f"  {phase}: {session_id}")


def dump_session(project_dir: Path, phase: str, attempt: int = 1) -> None:
    """Dump a phase session transcript."""
    sessions_dir = project_dir / ".orchestrator" / "sessions"

    if not sessions_dir.exists():
        print(f"No sessions directory at {sessions_dir}", file=sys.stderr)
        sys.exit(1)

    # Session files follow the pattern: <phase>-<attempt>.json
    session_file = sessions_dir / f"{phase}-{attempt}.json"

    if not session_file.exists():
        # Try to find any session for this phase
        matching = sorted(sessions_dir.glob(f"{phase}-*.json"))
        if matching:
            session_file = matching[-1]
            print(f"Using latest session: {session_file.name}", file=sys.stderr)
        else:
            print(
                f"Session not found: {session_file}. "
                f"Available: {[f.name for f in sorted(sessions_dir.glob('*'))]}",
                file=sys.stderr,
            )
            sys.exit(1)

    session_data = json.loads(session_file.read_text(encoding="utf-8"))
    print(json.dumps(session_data, indent=2, default=str))


def show_tokens(project_dir: Path) -> None:
    """Show per-phase token usage from log files."""
    logs_dir = project_dir / ".orchestrator" / "logs"

    if not logs_dir.exists():
        print("No logs directory found.", file=sys.stderr)
        sys.exit(1)

    phases = {}

    for log_file in sorted(logs_dir.glob("*.jsonl")):
        phase = log_file.stem
        total_prompt = 0
        total_completion = 0
        total_reasoning = 0
        call_count = 0

        for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only count LLM call entries
            if "prompt_tokens" in entry and entry.get("event", "").startswith("llm_call"):
                total_prompt += entry.get("prompt_tokens", 0) or 0
                total_completion += entry.get("completion_tokens", 0) or 0
                total_reasoning += entry.get("reasoning_tokens", 0) or 0
                call_count += 1

        phases[phase] = {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "reasoning_tokens": total_reasoning,
            "total_tokens": total_prompt + total_completion + total_reasoning,
            "call_count": call_count,
        }

    if not phases:
        print("No LLM call data found in logs.", file=sys.stderr)
        return

    print(f"Project: {project_dir.name}")
    print()
    print(f"{'Phase':<20} {'Calls':<8} {'Prompt':<12} {'Completion':<12} {'Reasoning':<12} {'Total':<12}")
    print("-" * 76)

    grand_total = {"prompt": 0, "completion": 0, "reasoning": 0, "total": 0, "calls": 0}

    for phase, tokens in phases.items():
        print(
            f"{phase:<20} {tokens['call_count']:<8} "
            f"{tokens['prompt_tokens']:<12} {tokens['completion_tokens']:<12} "
            f"{tokens['reasoning_tokens']:<12} {tokens['total_tokens']:<12}"
        )
        grand_total["prompt"] += tokens["prompt_tokens"]
        grand_total["completion"] += tokens["completion_tokens"]
        grand_total["reasoning"] += tokens["reasoning_tokens"]
        grand_total["total"] += tokens["total_tokens"]
        grand_total["calls"] += tokens["call_count"]

    print("-" * 76)
    print(
        f"{'Total':<20} {grand_total['calls']:<8} "
        f"{grand_total['prompt']:<12} {grand_total['completion']:<12} "
        f"{grand_total['reasoning']:<12} {grand_total['total']:<12}"
    )


def show_costs(project_dir: Path) -> None:
    """Show the per-run cost + token rollup from raw-io.jsonl + usage.jsonl."""
    from orchestrator.lib.usage_summary import rollup

    summary = rollup(project_dir)

    if summary.totals.call_count == 0:
        print("No reconciled LLM calls found.", file=sys.stderr)
        if summary.orphans["raw_io_only"] or summary.orphans["usage_only"]:
            print(f"Orphans — raw-io only: {len(summary.orphans['raw_io_only'])}, "
                  f"usage only: {len(summary.orphans['usage_only'])}",
                  file=sys.stderr)
        return

    print(f"Project: {project_dir.name}")
    print()
    print(f"{'Role':<14} {'Calls':<8} {'Prompt':<10} {'Compl':<10} "
          f"{'Reason':<10} {'Total':<10} {'Cost USD':<12} {'Latency ms':<12}")
    print("-" * 96)
    for role, t in sorted(summary.per_role.items()):
        print(f"{role:<14} {t.call_count:<8} {t.prompt_tokens:<10} "
              f"{t.completion_tokens:<10} {t.reasoning_tokens:<10} "
              f"{t.total_tokens:<10} {t.cost_usd:<12.6f} {t.latency_ms:<12.1f}")

    print("-" * 96)
    tt = summary.totals
    print(f"{'Total':<14} {tt.call_count:<8} {tt.prompt_tokens:<10} "
          f"{tt.completion_tokens:<10} {tt.reasoning_tokens:<10} "
          f"{tt.total_tokens:<10} {tt.cost_usd:<12.6f} {tt.latency_ms:<12.1f}")

    if summary.orphans["raw_io_only"] or summary.orphans["usage_only"]:
        print()
        print(f"Orphans — raw-io only: {len(summary.orphans['raw_io_only'])}, "
              f"usage only: {len(summary.orphans['usage_only'])}")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="AI Orchestrator CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # inspect subcommand
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect project state, sessions, and token usage",
    )
    inspect_parser.add_argument(
        "project_id",
        help="Project directory or project name",
    )
    inspect_parser.add_argument(
        "--phase",
        help="Dump session transcript for a specific phase",
    )
    inspect_parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Session attempt number (default: 1)",
    )
    inspect_parser.add_argument(
        "--tokens",
        action="store_true",
        help="Show per-phase token usage",
    )
    inspect_parser.add_argument(
        "--costs",
        action="store_true",
        help="Show per-role cost + token rollup (joins raw-io.jsonl + usage.jsonl)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the orchestrator CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "inspect":
        parser.print_help()
        sys.exit(1)

    try:
        project_dir = find_project(args.project_id)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.phase:
        dump_session(project_dir, args.phase, args.attempt)
    elif args.tokens:
        show_tokens(project_dir)
    elif args.costs:
        show_costs(project_dir)
    else:
        state = load_state(project_dir)
        list_phases(state, project_dir)


if __name__ == "__main__":
    main()
