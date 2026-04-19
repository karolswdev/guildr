"""Top-level guildr CLI.

Dispatches between subcommands. Run via the `guildr` console script
(declared in pyproject.toml), `orchestrate` (legacy alias), or
`python -m orchestrator`. The displayed program name follows whichever
binary the user actually invoked.
"""

from __future__ import annotations

import argparse
import os
import sys

from orchestrator.cli import inspect as inspect_cmd
from orchestrator.cli.run import add_run_subparser, cmd_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]) or "guildr",
        description="guildr — AI orchestrator for single-model SDLC automation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_run_subparser(subparsers)

    inspect_p = subparsers.add_parser(
        "inspect",
        help="Inspect project state, sessions, and token usage",
    )
    inspect_p.add_argument("project_id", help="Project directory or project name")
    inspect_p.add_argument("--phase", help="Dump session transcript for a specific phase")
    inspect_p.add_argument("--attempt", type=int, default=1, help="Session attempt (default: 1)")
    inspect_p.add_argument("--tokens", action="store_true", help="Show per-phase token usage")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "inspect":
        try:
            project_dir = inspect_cmd.find_project(args.project_id)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.phase:
            inspect_cmd.dump_session(project_dir, args.phase, args.attempt)
        elif args.tokens:
            inspect_cmd.show_tokens(project_dir)
        else:
            state = inspect_cmd.load_state(project_dir)
            inspect_cmd.list_phases(state, project_dir)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
