"""Deployer role — produces DEPLOY.md with deployment plan."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from orchestrator.lib.llm import LLMClient
from orchestrator.lib.state import State
from orchestrator.roles.base import BaseRole

logger = logging.getLogger(__name__)


class DeployerError(Exception):
    """Raised when the Deployer encounters a fatal error."""


# Deployment config files to detect
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


class Deployer(BaseRole):
    """Produces DEPLOY.md with deployment plan and environment requirements."""

    # -- public API ----------------------------------------------------------

    def execute(self, review_path: str = "REVIEW.md") -> str:
        """Execute deployment planning.

        Returns the path to DEPLOY.md.
        Raises DeployerError on fatal failure.
        """
        review_text = self._load_review(review_path)
        configs = self._detect_deploy_configs()
        env_vars = self._detect_env_vars()

        system_prompt = self._load_prompt("deployer", "generate")
        user_prompt = system_prompt.format(
            configs=configs,
            env_vars=env_vars,
            review_verdict=review_text,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._chat(messages)
        except Exception as exc:
            raise DeployerError(f"LLM call failed: {exc}") from exc

        # The LLM produces DEPLOY.md content; write it directly
        deploy_content = response.content.strip()
        self.state.write_file("DEPLOY.md", deploy_content)
        return "DEPLOY.md"

    # -- data detection ------------------------------------------------------

    def _detect_deploy_configs(self) -> str:
        """Detect deployment config files in the project directory."""
        found = []
        for config_file in _DEPLOY_CONFIGS:
            path = self.state.project_dir / config_file
            if path.exists():
                found.append(config_file)

        if found:
            return "\n".join(f"- {f}" for f in found)
        return "No deployment configs detected."

    def _detect_env_vars(self) -> list[str]:
        """Detect required environment variables from source code.

        Grep for os.environ, os.getenv, os.environ.get patterns.
        Only returns variable NAMES, never values.
        """
        env_vars: set[str] = set()
        project_dir = self.state.project_dir

        # Patterns to match environment variable access
        # Named-group patterns (capture group named 'var')
        named_patterns = [
            r"os\.environ\[[\'\"](?P<var>\w+)[\'\"]\]",
            r"os\.getenv\([\'\"](?P<var>\w+)[\'\"]",
            r"os\.environ\.get\([\'\"](?P<var>\w+)[\'\"]",
            r"getenv\([\'\"](?P<var>\w+)[\'\"]",
            r"env\.get\([\'\"](?P<var>\w+)[\'\"]",
        ]
        # Simple word patterns (match the whole thing)
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
            # Skip hidden dirs and venv
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
        """Load REVIEW.md content."""
        try:
            return self.state.read_file(path)
        except FileNotFoundError:
            return "No review available."

    # -- convenience ---------------------------------------------------------

    def get_required_env_vars(self) -> list[str]:
        """Return detected required environment variables.

        This is a convenience method for the orchestrator to use
        when setting up the deployment environment.
        """
        return self._detect_env_vars()
