"""Run the orchestrator from the terminal.

Usage:
    orchestrate run --config config.yaml
    orchestrate run --config config.yaml --dry-run
    orchestrate run --from-env --dry-run
    orchestrate run --config config.yaml --project /path/to/project --no-gates
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from orchestrator.engine import Orchestrator, PhaseFailure
from orchestrator.lib.config import Config


_DRY_RUN_LLAMA_URL = "http://dry-run.invalid"


def add_run_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `run` subcommand into a top-level parser."""
    p = subparsers.add_parser(
        "run",
        help="Execute the full SDLC pipeline against a project",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--config",
        type=Path,
        help="Path to a YAML config file (see config.example.yaml).",
    )
    src.add_argument(
        "--from-env",
        action="store_true",
        help="Build config from environment variables (LLAMA_SERVER_URL, PROJECT_DIR, ...).",
    )
    p.add_argument(
        "--project",
        type=Path,
        help="Override project_dir from the config.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Use FakeLLMClient with canned responses; do not contact any LLM server.",
    )
    gate_group = p.add_mutually_exclusive_group()
    gate_group.add_argument(
        "--gate",
        action="store_true",
        help="Attended run: block at every human gate until approved (sets require_human_approval=True).",
    )
    gate_group.add_argument(
        "--no-gates",
        action="store_true",
        help="Idle-RPG run: auto-approve all human gates (sets require_human_approval=False). Default unless --gate is passed.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="DEBUG-level logging.",
    )


def _load_config(args: argparse.Namespace) -> Config:
    if args.config is not None:
        cfg = Config.from_yaml(args.config)
        cfg = cfg.with_env_overrides()
    elif args.dry_run and not (
        os.environ.get("LLAMA_SERVER_URL")
        or os.environ.get("LLAMA_URL")
        or os.environ.get("LLAMA_PRIMARY_URL")
    ):
        project_dir = os.environ.get(
            "PROJECT_DIR", os.environ.get("ORCHESTRATOR_PROJECT_DIR", ".")
        )
        cfg = Config(
            llama_server_url=_DRY_RUN_LLAMA_URL,
            project_dir=Path(project_dir),
        ).with_env_overrides()
    else:
        cfg = Config.from_env()
    if args.project is not None:
        cfg.project_dir = args.project
    if args.gate:
        cfg.require_human_approval = True
    elif args.no_gates:
        cfg.require_human_approval = False
    return cfg


def _build_opencode_session_runners(
    endpoints_cfg: object, project_dir: Path
) -> dict[str, object]:
    """Wire opencode-driven roles to fresh ``OpencodeSession`` instances.

    Writes the per-project ``opencode.json`` from the declared
    endpoints config (H6.1), then builds one ``OpencodeSession`` per
    opencode-driven role (H6.3a — coder only, for now). Each session
    resolves its provider + model from that role's first routing entry
    so `--model <provider>/<modelID>` matches what the pool would have
    chosen.
    """
    from orchestrator.lib.opencode import OpencodeSession
    from orchestrator.lib.opencode_config import write_opencode_config

    config_path = write_opencode_config(endpoints_cfg, project_dir)  # type: ignore[arg-type]
    endpoints_by_name = {ep.name: ep for ep in endpoints_cfg.endpoints}  # type: ignore[attr-defined]

    runners: dict[str, object] = {}
    for role in ("architect", "judge", "coder", "tester", "reviewer", "narrator", "deployer"):
        routes = endpoints_cfg.routing.get(role) or []  # type: ignore[attr-defined]
        # Judge re-uses architect's routing by default — operators rarely
        # declare a separate line for it and the rubric doubles as a
        # smaller-model task on the same endpoint.
        if not routes and role == "judge":
            routes = endpoints_cfg.routing.get("architect") or []  # type: ignore[attr-defined]
        if not routes:
            continue
        entry = routes[0]
        ep = endpoints_by_name[entry.endpoint]
        runners[role] = OpencodeSession(
            project_dir=project_dir,
            config_path=config_path,
            provider=ep.name,
            model=entry.model or ep.model,
            agent=role,
        )
    return runners


def cmd_run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("orchestrator.cli.run")

    cfg = _load_config(args)
    cfg.project_dir = cfg.project_dir.expanduser().resolve()
    cfg.project_dir.mkdir(parents=True, exist_ok=True)

    endpoints_cfg = None
    if args.config is not None and not args.dry_run:
        from orchestrator.lib.endpoints import load_endpoints_from_yaml
        endpoints_cfg = load_endpoints_from_yaml(args.config)

    orch_kwargs: dict[str, object] = {"config": cfg}
    if args.dry_run:
        orch_kwargs["dry_run"] = True
        mode = "dry-run"
    elif endpoints_cfg is not None:
        orch_kwargs["session_runners"] = _build_opencode_session_runners(
            endpoints_cfg, cfg.project_dir
        )
        mode = f"live/opencode[{','.join(e.name for e in endpoints_cfg.endpoints)}]"
    else:
        log.error(
            "Live runs require a config file with an 'endpoints:' block "
            "(opencode-backed routing). The legacy single-endpoint LLMClient "
            "path was removed with the pool-machinery sunset."
        )
        return 2

    log.info(
        "Starting orchestrator: project=%s mode=%s gates=%s",
        cfg.project_dir,
        mode,
        "on" if cfg.require_human_approval else "off",
    )

    orchestrator = Orchestrator(**orch_kwargs)
    try:
        orchestrator.run()
    except PhaseFailure as exc:
        log.error("Pipeline failed: %s", exc)
        return 1
    log.info("Pipeline complete. Project directory: %s", cfg.project_dir)
    return 0
