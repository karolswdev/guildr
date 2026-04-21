"""Escalation role for external expert CLI/API remediation plans."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from orchestrator.lib.control import write_compact_context
from orchestrator.lib.state import State


@dataclass
class GuruEscalation:
    """Ask stronger external advisors for a remediation plan only."""

    state: State
    step_config: dict[str, Any] | None = None
    _phase_logger: Any = None
    _phase: str = "guru_escalation"
    _role: str = "guru_escalation"

    def execute(self) -> str:
        write_compact_context(self.state.project_dir, max_chars=18000)
        phase_dir = self.state.project_dir / "phase-files" / "escalation"
        phase_dir.mkdir(parents=True, exist_ok=True)

        prompt = self._build_prompt()
        config = self.step_config or {}
        providers = config.get("providers")
        if not isinstance(providers, list) or not providers:
            providers = [
                {"kind": "codex"},
                {"kind": "claude"},
                {"kind": "openrouter"},
            ]

        results: list[dict[str, Any]] = []
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            kind = str(provider.get("kind", "")).strip().lower()
            if not kind:
                continue
            if kind == "codex":
                results.append(self._run_codex(prompt, phase_dir, provider))
            elif kind == "claude":
                results.append(self._run_claude(prompt, phase_dir, provider))
            elif kind == "openrouter":
                results.append(self._run_openrouter(prompt, phase_dir, provider))

        summary_path = phase_dir / "COUNCIL.md"
        summary_path.write_text(self._render_summary(results), encoding="utf-8")
        self.state.write_file("ESCALATION_PLAN.md", summary_path.read_text(encoding="utf-8"))
        return "ESCALATION_PLAN.md"

    def _build_prompt(self) -> str:
        compact_path = self.state.project_dir / ".orchestrator" / "control" / "context.compact.md"
        compact = ""
        if compact_path.exists():
            compact = compact_path.read_text(encoding="utf-8", errors="replace")
        current_phase = self.state.current_phase or "unknown"
        return textwrap.dedent(
            f"""
            You are an external expert advisor helping an orchestrated local-model council unblock a project.

            Constraints:
            - Produce a remediation plan only. Do not modify files.
            - Optimize for sub-128k local execution after handoff.
            - Break the plan into atomic, verifiable steps.
            - Call out the likely failure mode and the minimum context each step needs.
            - Include specific safety nets, retry points, and checkpoints.

            Current orchestrator phase: {current_phase}
            Project root: {self.state.project_dir}

            Compact project context:
            {compact}
            """
        ).strip()

    def _run_codex(self, prompt: str, phase_dir: Path, provider: dict[str, Any]) -> dict[str, Any]:
        binary = shutil.which("codex")
        output_path = phase_dir / "codex.md"
        if not binary:
            return {"provider": "codex", "status": "missing"}
        command = [
            binary,
            "exec",
            "-C",
            str(self.state.project_dir),
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
            prompt,
        ]
        return self._run_command("codex", command, output_path)

    def _run_claude(self, prompt: str, phase_dir: Path, provider: dict[str, Any]) -> dict[str, Any]:
        binary = shutil.which("claude")
        output_path = phase_dir / "claude.md"
        if not binary:
            return {"provider": "claude", "status": "missing"}
        command = [
            binary,
            "-p",
            "--permission-mode",
            "plan",
            "--output-format",
            "text",
            "--add-dir",
            str(self.state.project_dir),
            prompt,
        ]
        return self._run_command("claude", command, output_path)

    def _run_openrouter(self, prompt: str, phase_dir: Path, provider: dict[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        model = str(provider.get("model") or os.environ.get("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4.1-mini")).strip()
        output_path = phase_dir / "openrouter.md"
        if not api_key:
            return {"provider": "openrouter", "status": "missing_api_key", "model": model}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        title = os.environ.get("OPENROUTER_APP_NAME", "guildr")
        if title:
            headers["X-Title"] = title
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return a terse remediation plan in markdown. Do not ask follow-up questions."},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {"provider": "openrouter", "status": "error", "error": str(exc), "model": model}

        content = ""
        try:
            choices = data.get("choices") or []
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
        except Exception:
            content = ""
        if not content.strip():
            return {"provider": "openrouter", "status": "empty", "model": model}
        output_path.write_text(content, encoding="utf-8")
        return {"provider": "openrouter", "status": "ok", "model": model, "path": str(output_path.relative_to(self.state.project_dir))}

    def _run_command(self, provider_name: str, command: list[str], output_path: Path) -> dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                cwd=self.state.project_dir,
                capture_output=True,
                text=True,
                timeout=240,
            )
        except Exception as exc:
            return {"provider": provider_name, "status": "error", "error": str(exc)}
        if result.returncode != 0:
            return {
                "provider": provider_name,
                "status": "error",
                "error": (result.stderr or result.stdout or f"exit {result.returncode}").strip()[:1200],
            }
        if not output_path.exists():
            if result.stdout.strip():
                output_path.write_text(result.stdout, encoding="utf-8")
            else:
                return {"provider": provider_name, "status": "empty"}
        return {"provider": provider_name, "status": "ok", "path": str(output_path.relative_to(self.state.project_dir))}

    @staticmethod
    def _render_summary(results: list[dict[str, Any]]) -> str:
        lines = [
            "# Escalated Resolution Council",
            "",
            "External advisor runs intended to unblock the local-model workflow.",
            "",
        ]
        for result in results:
            provider = result.get("provider", "unknown")
            status = result.get("status", "unknown")
            lines.append(f"## {provider}")
            lines.append(f"- Status: {status}")
            if result.get("model"):
                lines.append(f"- Model: {result['model']}")
            if result.get("path"):
                lines.append(f"- Artifact: `{result['path']}`")
            if result.get("error"):
                lines.append(f"- Error: {result['error']}")
            lines.append("")
        ok_paths = [r["path"] for r in results if r.get("status") == "ok" and r.get("path")]
        if ok_paths:
            lines.append("## Recommended Handoff")
            lines.append("")
            lines.append("- Feed the strongest remediation plan back into micro-task packets.")
            lines.append("- Resume from the blocked phase with one explicit operator instruction.")
            lines.append("- Keep the escalation artifacts visible for audit and replay.")
            lines.append("")
        else:
            lines.append("No external advisor completed successfully.")
            lines.append("")
        return "\n".join(lines).strip() + "\n"
