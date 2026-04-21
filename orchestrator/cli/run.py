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


_DRY_RUN_SPRINT_PLAN = (
    "# Sprint Plan (dry-run)\n\n"
    "## Overview\n"
    "Dry-run uses a single tiny slice that still preserves traceability.\n\n"
    "## Memory Tiers\n"
    "- **Global Memory:** dry-run stays self-contained and verifier-safe.\n"
    "- **Sprint Memory:** produce one README artifact and verify it from the shell.\n"
    "- **Task Packet Memory:** remember the target file, evidence command, and expected output.\n\n"
    "## Traceability Matrix\n"
    "- `REQ-1` -> Task 1\n"
    "- `RISK-1` -> Task 1\n\n"
    "## Architecture Decisions\n"
    "- Keep dry-run self-contained.\n\n"
    "## Tasks\n\n"
    "### Task 1: bootstrap\n"
    "- **Priority**: P0\n"
    "- **Dependencies**: none\n"
    "- **Files**: `README.md`\n\n"
    "**Acceptance Criteria:**\n"
    "- [ ] README exists\n\n"
    "**Evidence Required:**\n"
    "- Run `ls README.md`\n\n"
    "**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)\n"
    "- [ ] README.md check pending\n\n"
    "**Implementation Notes:**\n"
    "Source Requirements: `REQ-1`, `RISK-1`\n"
    "Task Memory: Create README.md and keep verification bounded to a single ls command.\n"
    "Determinism Notes: Only README.md may change; verifier expects README.md to exist.\n\n"
    "## Risks & Mitigations\n"
    "1. None - dry-run fixture only.\n"
)

_DRY_RUN_JUDGE_JSON = (
    '{"specificity":{"score":1,"issues":[]},'
    '"testability":{"score":1,"issues":[]},'
    '"evidence":{"score":1,"issues":[]},'
    '"completeness":{"score":1,"issues":[]},'
    '"feasibility":{"score":1,"issues":[]},'
    '"risk":{"score":1,"issues":[]}}'
)

_DRY_RUN_TESTER_REPORT = (
    "### Task 1: bootstrap\n"
    "- Status: VERIFIED\n"
    "- Evidence 1: PASS — README.md\n"
    "- Notes: dry-run\n"
)

_DRY_RUN_DEPLOY_REPORT = (
    "# DEPLOY (dry-run)\n\n"
    "1. Deployment target: local\n"
    "2. Required env vars: none\n"
    "3. Manual steps: none\n"
    "4. Smoke-test commands: ls README.md\n"
)


def _build_dry_run_llm() -> object:
    """Build a content-aware fake LLM for dry-run mode.

    Different role calls have different output shape requirements
    (markdown plan, strict JSON judge, file-list JSON for coder, etc.).
    A flat role→response map collides because every call's last message
    role is "user". So we dispatch on system-prompt content instead.
    """
    from orchestrator.lib.llm import LLMResponse
    from orchestrator.lib.llm_fake import FakeLLMClient

    def _r(content: str) -> LLMResponse:
        return LLMResponse(
            content=content,
            reasoning="",
            prompt_tokens=0,
            completion_tokens=max(1, len(content.split())),
            reasoning_tokens=0,
            finish_reason="stop",
        )

    class _ContentAwareFake(FakeLLMClient):
        def chat(self, messages, **kw):  # type: ignore[override]
            self.call_count += 1
            sys_content = ""
            for m in messages:
                if m.get("role") == "system":
                    sys_content = m.get("content", "")
                    break
            sys_lower = sys_content.lower()
            # Order matters — check most specific markers first.
            if "skeptical senior engineering manager" in sys_lower:
                return _r(_DRY_RUN_JUDGE_JSON)
            if "you are a qa engineer" in sys_lower:
                return _r(_DRY_RUN_TESTER_REPORT)
            if "you are a devops engineer" in sys_lower:
                return _r(_DRY_RUN_DEPLOY_REPORT)
            return _r(_DRY_RUN_SPRINT_PLAN)

    return _ContentAwareFake()


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
    for role in ("coder", "reviewer"):
        routes = endpoints_cfg.routing.get(role) or []  # type: ignore[attr-defined]
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


def _build_real_llm(cfg: Config) -> object:
    """Construct a single-endpoint sync LLMClient for legacy configs.

    Used when ``config.yaml`` declares only ``llama_server_url`` and no
    ``endpoints:`` block. Multi-endpoint configs are built via
    ``orchestrator.lib.endpoints.build_pool`` and passed to
    ``Orchestrator(pool=...)`` instead.
    """
    from orchestrator.lib.llm import LLMClient

    return LLMClient(base_url=cfg.llama_server_url)


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
        orch_kwargs["fake_llm"] = _build_dry_run_llm()
        mode = "dry-run"
    elif endpoints_cfg is not None:
        from orchestrator.lib.endpoints import build_pool
        orch_kwargs["pool"] = build_pool(endpoints_cfg)
        orch_kwargs["session_runners"] = _build_opencode_session_runners(
            endpoints_cfg, cfg.project_dir
        )
        mode = f"live/pool[{','.join(e.name for e in endpoints_cfg.endpoints)}]"
    else:
        orch_kwargs["fake_llm"] = _build_real_llm(cfg)
        mode = "live/single-endpoint"

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
