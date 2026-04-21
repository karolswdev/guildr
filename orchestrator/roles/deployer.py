"""Deployer role — produces DEPLOY.md via opencode (H6.3d).

One opencode session per deployment-planning pass. Input is the
detected deploy configs, the env vars we grepped out of the source
tree, and the Reviewer's verdict. Output is the canonical DEPLOY.md
text — the role writes it deterministically from
``result.assistant_text`` rather than trusting an agent tool call,
because downstream readers assume an exact file path and structure.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from orchestrator.lib.control import append_operator_context
from orchestrator.lib.opencode import SessionRunner
from orchestrator.lib.opencode_audit import emit_session_audit
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class DeployerError(Exception):
    """Raised when the Deployer cannot complete its session."""


_DEPLOY_CONFIGS = [
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "fly.toml",
    "railway.json",
    ".railway/config.json",
    "render.yaml",
    "app.json",
    "Gulpfile.js",
    "serverless.yml",
    "serverless.yaml",
    "netlify.toml",
    "vercel.json",
    "Procfile",
    "ecosystem.config.js",
    "Pipfile",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
]


class Deployer:
    """Produces DEPLOY.md via one opencode session."""

    _phase: str = "deployment"
    _role: str = "deployer"

    def __init__(
        self,
        runner: SessionRunner,
        state: State,
        phase_logger: Any = None,
    ) -> None:
        self.runner = runner
        self.state = state
        self._phase_logger = phase_logger

    # -- public API ----------------------------------------------------------

    def execute(self, review_path: str = "REVIEW.md") -> str:
        review_text = self._load_review(review_path)
        configs = self._detect_deploy_configs()
        env_vars = self._detect_env_vars()

        template = self._load_prompt("deployer", "generate")
        prompt = template.format(
            configs=configs,
            env_vars=env_vars,
            review_verdict=review_text,
        )
        prompt = self._augment_prompt(prompt)

        try:
            result = self.runner.run(prompt)
        except Exception as exc:
            raise DeployerError(f"opencode session failed: {exc}") from exc

        emit_session_audit(
            self.state,
            result,
            role=self._role,
            phase=self._phase,
            step=self._phase,
            prompt=prompt,
        )

        if result.exit_code != 0:
            raise DeployerError(
                f"opencode session exited with rc={result.exit_code}: "
                f"{result.assistant_text[:200]!r}"
            )

        deploy_content = result.assistant_text.strip()
        if not deploy_content:
            raise DeployerError(
                "opencode session returned no assistant text — nothing to write"
            )
        self.state.write_file("DEPLOY.md", deploy_content)
        return "DEPLOY.md"

    # -- data detection ------------------------------------------------------

    def _detect_deploy_configs(self) -> str:
        found = []
        for config_file in _DEPLOY_CONFIGS:
            path = self.state.project_dir / config_file
            if path.exists():
                found.append(config_file)
        if found:
            return "\n".join(f"- {f}" for f in found)
        return "No deployment configs detected."

    def _detect_env_vars(self) -> list[str]:
        """Grep the source tree for env var access.

        Returns variable *names* only — values are never read or recorded.
        """
        env_vars: set[str] = set()
        project_dir = self.state.project_dir

        named_patterns = [
            r"os\.environ\[[\'\"](?P<var>\w+)[\'\"]\]",
            r"os\.getenv\([\'\"](?P<var>\w+)[\'\"]",
            r"os\.environ\.get\([\'\"](?P<var>\w+)[\'\"]",
            r"getenv\([\'\"](?P<var>\w+)[\'\"]",
            r"env\.get\([\'\"](?P<var>\w+)[\'\"]",
        ]
        word_patterns = [
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SECRET_KEY)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>API_KEY)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>DATABASE_URL)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>DATABASE_HOST)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>DATABASE_PORT)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>DATABASE_NAME)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>DATABASE_USER)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>DATABASE_PASSWORD)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>REDIS_URL)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>JWT_SECRET)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>JWT_EXPIRY)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SMTP_HOST)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SMTP_PORT)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SMTP_USER)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SMTP_PASSWORD)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>AWS_ACCESS_KEY)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>AWS_SECRET_KEY)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>AWS_REGION)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SLACK_WEBHOOK)(?:[^a-zA-Z0-9_]|$)",
            r"(?:^|[^a-zA-Z0-9_])(?P<var>SENTRY_DSN)(?:[^a-zA-Z0-9_]|$)",
        ]

        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in ("__pycache__", ".venv", "node_modules")
            ]
            for filename in files:
                if not filename.endswith((".py", ".js", ".ts", ".yml", ".yaml", ".json", ".toml")):
                    continue
                filepath = Path(root) / filename
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    for pattern in named_patterns + word_patterns:
                        for match in re.finditer(pattern, content):
                            var_name = match.group("var")
                            if var_name and not var_name.startswith("_"):
                                env_vars.add(var_name)
                except (OSError, UnicodeDecodeError):
                    continue

        return sorted(env_vars) if env_vars else ["No environment variables detected."]

    def _load_review(self, path: str) -> str:
        try:
            return self.state.read_file(path)
        except FileNotFoundError:
            return "No review available."

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _load_prompt(role: str, name: str) -> str:
        return (_PROMPT_DIR / role / f"{name}.txt").read_text(encoding="utf-8")

    def _augment_prompt(self, prompt: str) -> str:
        return append_operator_context(self.state.project_dir, self._phase, prompt)

    # -- convenience ---------------------------------------------------------

    def get_required_env_vars(self) -> list[str]:
        return self._detect_env_vars()
