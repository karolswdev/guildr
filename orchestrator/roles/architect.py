"""Architect role — produces sprint-plan.md via opencode (H6.3e).

Two opencode sessions per execute() pass: one ``architect`` session
generates/refines the sprint plan, one ``judge`` session scores it
against the rubric. Both agents run with every tool disabled (see
``opencode_config.build_agent_definitions``) — they are strict
text/JSON completions. The multi-attempt JSON-repair loop inside
``_self_evaluate`` fires fresh judge sessions rather than continuing
one, because our ``SessionRunner`` protocol is stateless by design.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.lib.config import Config
from orchestrator.lib.control import append_operator_context
from orchestrator.lib.opencode import SessionRunner
from orchestrator.lib.opencode_audit import emit_session_audit
from orchestrator.lib.sprint_plan import parse_tasks
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "architect"


class ArchitectFailure(Exception):
    """Raised when the Architect exhausts all retry passes."""


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


@dataclass
class Architect:
    """Generates and self-evaluates sprint plans via opencode sessions."""

    runner: SessionRunner
    judge_runner: SessionRunner
    state: State
    config: Config
    _phase_logger: Any = None
    _phase: str = "architect"
    _role: str = "architect"
    EVALUATION_CRITERIA: list[str] = field(
        default_factory=lambda: [
            "specificity", "testability", "evidence",
            "completeness", "feasibility", "risk",
        ],
        init=False,
        repr=False,
    )
    MANDATORY: set[str] = field(
        default_factory=lambda: {"testability", "evidence"},
        init=False,
        repr=False,
    )

    # -- public API ----------------------------------------------------------

    def execute(self) -> str:
        """Legacy single-phase entry point: plan + refine back-to-back.

        Kept for workflow.json files still pinning the combined
        ``architect`` handler. The H6.5 default workflow instead calls
        ``plan()``, fires the ``approve_plan_draft`` gate, then calls
        ``refine()`` — with a human decision point between the two.
        """
        status = self.plan()
        if status["status"] == "done":
            return "sprint-plan.md"
        return self.refine()

    def plan(self) -> dict[str, Any]:
        """Run pass 1 only: generate + judge.

        If the first draft passes the rubric, writes ``sprint-plan.md``
        and stashes a status file flagged ``done``. Otherwise writes the
        draft + eval under ``.orchestrator/drafts/`` and stashes the
        status as ``needs_refine`` so ``refine()`` can pick up where we
        left off in a later phase.
        """
        qwendea = self.state.read_file("qwendea.md")
        plan = self._generate(qwendea)
        score, evaluation = self._self_evaluate(qwendea, plan)

        if self._passes(score, evaluation):
            self.state.write_file("sprint-plan.md", plan)
            status = {"status": "done", "score": score, "pass_num": 1}
            self._write_plan_status(status)
            return status

        self._write_draft(1, plan, evaluation)
        status = {
            "status": "needs_refine",
            "score": score,
            "pass_num": 1,
            "best_draft": "architect-pass-1.md",
            "best_eval": "architect-pass-1-eval.json",
        }
        self._write_plan_status(status)
        return status

    def refine(self) -> str:
        """Run passes 2..max_passes if ``plan()`` flagged needs_refine.

        No-op when the status file is missing or already ``done``.
        Escalates (and raises ``ArchitectFailure``) when every pass fails
        the rubric.
        """
        status = self._read_plan_status()
        if status is None or status.get("status") == "done":
            return "sprint-plan.md"

        qwendea = self.state.read_file("qwendea.md")
        drafts = self._load_saved_drafts(status)
        best_plan, best_score, best_eval = drafts[-1]

        for pass_num in range(2, self.config.architect_max_passes + 1):
            plan = self._refine(qwendea, best_plan, best_eval)
            score, evaluation = self._self_evaluate(qwendea, plan)
            drafts.append((plan, score, evaluation))
            self._write_draft(pass_num, plan, evaluation)

            if self._passes(score, evaluation):
                self.state.write_file("sprint-plan.md", plan)
                self._write_plan_status(
                    {"status": "done", "score": score, "pass_num": pass_num}
                )
                return "sprint-plan.md"

            if score > best_score:
                best_plan = plan
                best_score = score
                best_eval = evaluation

        self._escalate(drafts)
        raise ArchitectFailure(
            f"Architect failed after {self.config.architect_max_passes} "
            f"passes (best score: {best_score}/6)"
        )

    # -- plan/refine status + draft persistence ------------------------------

    def _plan_status_path(self) -> Path:
        return self.state.project_dir / ".orchestrator" / "drafts" / "architect-plan-status.json"

    def _write_plan_status(self, status: dict[str, Any]) -> None:
        path = self._plan_status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, indent=2), encoding="utf-8")

    def _read_plan_status(self) -> dict[str, Any] | None:
        path = self._plan_status_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return None

    def _write_draft(self, pass_num: int, plan: str, evaluation: dict[str, Any]) -> None:
        drafts_dir = self.state.project_dir / ".orchestrator" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        (drafts_dir / f"architect-pass-{pass_num}.md").write_text(plan, encoding="utf-8")
        (drafts_dir / f"architect-pass-{pass_num}-eval.json").write_text(
            json.dumps(evaluation, indent=2), encoding="utf-8"
        )

    def _load_saved_drafts(
        self, status: dict[str, Any]
    ) -> list[tuple[str, int, dict[str, Any]]]:
        drafts_dir = self.state.project_dir / ".orchestrator" / "drafts"
        drafts: list[tuple[str, int, dict[str, Any]]] = []
        pass_num = 1
        while True:
            plan_path = drafts_dir / f"architect-pass-{pass_num}.md"
            eval_path = drafts_dir / f"architect-pass-{pass_num}-eval.json"
            if not plan_path.exists() or not eval_path.exists():
                break
            plan = plan_path.read_text(encoding="utf-8")
            evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
            score, _ = self._compute_score(evaluation)
            drafts.append((plan, score, evaluation))
            pass_num += 1
        if not drafts:
            raise ArchitectFailure(
                "refine() called but no architect-pass-N.md drafts found on disk"
            )
        return drafts

    # -- generation ----------------------------------------------------------

    def _generate(self, qwendea: str) -> str:
        system_prompt = _load_prompt("generate")
        user_prompt = (
            f"Here is the project specification:\n\n"
            f"```\n{qwendea}\n```\n\n"
            f"Produce a sprint-plan.md following the structure specification."
        )
        user_prompt = self._append_forum_context(user_prompt)
        user_prompt = append_operator_context(
            self.state.project_dir,
            self._phase,
            user_prompt,
            events=getattr(self.state, "events", None),
        )
        prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
        return self._run_architect_session(prompt)

    def _refine(self, qwendea: str, prior: str, prior_eval: dict[str, Any]) -> str:
        system_prompt = _load_prompt("generate")
        refine_template = _load_prompt("refine")
        failures = self._format_failures(prior_eval)
        current_plan_text = f"Here is your previous sprint-plan.md:\n\n```\n{prior}\n```"
        failures_text = refine_template.format(failures=failures, current_plan=current_plan_text)
        failures_text = self._append_forum_context(failures_text)
        failures_text = append_operator_context(
            self.state.project_dir,
            self._phase,
            failures_text,
            events=getattr(self.state, "events", None),
        )
        prompt = f"{system_prompt}\n\n---\n\n{failures_text}"
        return self._run_architect_session(prompt)

    def _run_architect_session(self, prompt: str) -> str:
        try:
            result = self.runner.run(prompt)
        except Exception as exc:
            raise ArchitectFailure(f"opencode architect session failed: {exc}") from exc

        emit_session_audit(
            self.state,
            result,
            role=self._role,
            phase=self._phase,
            step=self._phase,
            prompt=prompt,
        )

        if result.exit_code != 0:
            raise ArchitectFailure(
                f"opencode architect session exited with rc={result.exit_code}: "
                f"{result.assistant_text[:200]!r}"
            )
        text = result.assistant_text.strip()
        if not text:
            raise ArchitectFailure(
                "opencode architect session returned no assistant text"
            )
        return text

    # -- self-evaluation -----------------------------------------------------

    def _self_evaluate(self, qwendea: str, plan: str) -> tuple[int, dict[str, Any]]:
        judge_prompt = _load_prompt("judge")
        user_prompt = (
            f"Here is the project specification:\n\n"
            f"```\n{qwendea}\n```\n\n"
            f"Here is the sprint plan to evaluate:\n\n"
            f"```\n{plan}\n```"
        )
        user_prompt = self._append_forum_context(user_prompt)
        user_prompt = append_operator_context(
            self.state.project_dir,
            self._phase,
            user_prompt,
            events=getattr(self.state, "events", None),
        )
        base_prompt = f"{judge_prompt}\n\n---\n\n{user_prompt}"

        # Attempt 1: strict parse on a fresh session.
        raw = self._call_judge(base_prompt)
        result = self._parse_json(raw)
        if result is not None:
            self._apply_local_plan_checks(plan, result)
            return self._compute_score(result)

        # Attempt 2: fresh session, prompt carries the previous malformed
        # output + a re-JSON directive. Sessions are stateless by design,
        # so "re-prompt" is just a new prompt with more context.
        repair_prompt = (
            f"{base_prompt}\n\n---\n\n"
            f"Your previous output was not valid JSON:\n\n"
            f"```\n{raw}\n```\n\n"
            f"Return only the JSON object, nothing else."
        )
        raw = self._call_judge(repair_prompt)
        result = self._parse_json(raw)
        if result is not None:
            self._apply_local_plan_checks(plan, result)
            return self._compute_score(result)

        # Attempt 3: regex salvage over the most-recent raw text.
        result = self._extract_json_regex(raw)
        if result is not None:
            self._apply_local_plan_checks(plan, result)
            return self._compute_score(result)

        logger.warning("Architect self-eval: all JSON parsing attempts failed")
        return 0, {"reason": "malformed"}

    def _call_judge(self, prompt: str) -> str:
        try:
            result = self.judge_runner.run(prompt)
        except Exception as exc:
            raise ArchitectFailure(f"opencode judge session failed: {exc}") from exc

        emit_session_audit(
            self.state,
            result,
            role="judge",
            phase=self._phase,
            step=self._phase,
            prompt=prompt,
        )

        if result.exit_code != 0:
            raise ArchitectFailure(
                f"opencode judge session exited with rc={result.exit_code}: "
                f"{result.assistant_text[:200]!r}"
            )
        return result.assistant_text

    # -- evaluation post-processing -----------------------------------------

    @classmethod
    def _apply_local_plan_checks(
        cls,
        plan: str,
        evaluation: dict[str, Any],
    ) -> None:
        completeness_issues = cls._plan_structure_issues(plan)
        specificity_issues: list[str] = []
        evidence_issues: list[str] = []
        for task in parse_tasks(plan):
            for evidence in task.evidence_required:
                issue = cls._evidence_issue(evidence)
                if issue:
                    evidence_issues.append(f"Task {task.id}: {issue}: {evidence}")
            task_issues = cls._task_traceability_issues(task.body)
            specificity_issues.extend(f"Task {task.id}: {issue}" for issue in task_issues)

        cls._merge_issues(evaluation, "completeness", completeness_issues)
        cls._merge_issues(evaluation, "specificity", specificity_issues)
        cls._merge_issues(evaluation, "evidence", evidence_issues)

    @staticmethod
    def _merge_issues(
        evaluation: dict[str, Any],
        criterion: str,
        issues: list[str],
    ) -> None:
        if not issues:
            return
        entry = evaluation.setdefault(criterion, {"score": 1, "issues": []})
        if not isinstance(entry, dict):
            entry = {"score": 1, "issues": []}
            evaluation[criterion] = entry
        entry["score"] = 0
        existing = entry.get("issues")
        if not isinstance(existing, list):
            existing = []
        entry["issues"] = existing + issues

    @staticmethod
    def _plan_structure_issues(plan: str) -> list[str]:
        issues: list[str] = []
        for section in ("## Memory Tiers", "## Traceability Matrix"):
            if section not in plan:
                issues.append(f"missing required section '{section}'")
        return issues

    @staticmethod
    def _task_traceability_issues(task_body: str) -> list[str]:
        issues: list[str] = []
        for marker in ("Source Requirements:", "Task Memory:", "Determinism Notes:"):
            if marker not in task_body:
                issues.append(f"missing '{marker}' in task notes")
        return issues

    @staticmethod
    def _evidence_issue(evidence: str) -> str | None:
        lowered = evidence.lower()
        if re.search(
            r"\b(npm|pnpm|yarn)\s+run\s+dev\b|\b(next|vite)\s+dev\b|\bwebpack\s+serve\b|\bpython\s+-m\s+http\.server\b|\buvicorn\b|^vite(?:\s|$)",
            lowered,
        ):
            return "long-running dev-server command is not verifier-safe"
        if re.search(r"\bobserve\b|\binspect\b|\bverify visually\b|\bbrowser\b|\bwindow\b", lowered):
            return "browser/manual observation is not automated evidence"
        return None

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    @staticmethod
    def _extract_json_regex(raw: str) -> dict[str, Any] | None:
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    @staticmethod
    def _compute_score(evaluation: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        score = 0
        for criterion in ["specificity", "testability", "evidence",
                          "completeness", "feasibility", "risk"]:
            entry = evaluation.get(criterion, {})
            if isinstance(entry, dict) and entry.get("score") == 1:
                score += 1
        return score, evaluation

    # -- pass/fail logic -----------------------------------------------------

    def _passes(self, score: int, evaluation: dict[str, Any]) -> bool:
        if score < self.config.architect_pass_threshold:
            return False
        for c in self.MANDATORY:
            entry = evaluation.get(c, {})
            if isinstance(entry, dict):
                if entry.get("score") != 1:
                    return False
            elif entry != 1:
                return False
        return True

    # -- escalation ----------------------------------------------------------

    def _escalate(self, drafts: list[tuple[str, int, dict[str, Any]]]) -> None:
        drafts_dir = self.state.project_dir / ".orchestrator" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        for i, (plan, score, evaluation) in enumerate(drafts, start=1):
            plan_path = drafts_dir / f"architect-pass-{i}.md"
            plan_path.write_text(plan, encoding="utf-8")

            eval_path = drafts_dir / f"architect-pass-{i}-eval.json"
            eval_path.write_text(
                json.dumps(evaluation, indent=2), encoding="utf-8"
            )

        escalation_path = self.state.project_dir / ".orchestrator" / "escalation.md"
        lines = [
            "# Architect Escalation",
            "",
            "The Architect failed to produce a passing sprint plan after "
            f"{len(drafts)} pass(es).",
            "",
            "## Summary",
            "",
        ]

        best_score = max(d[1] for d in drafts)
        lines.append(f"**Best score**: {best_score}/6")
        lines.append("")
        lines.append("## Drafts")
        lines.append("")

        for i, (plan, score, evaluation) in enumerate(drafts, start=1):
            lines.append(f"### Pass {i} (score: {score}/6)")
            lines.append("")
            for criterion in self.EVALUATION_CRITERIA:
                entry = evaluation.get(criterion, {})
                s = entry.get("score", 0) if isinstance(entry, dict) else 0
                status = "PASS" if s == 1 else "FAIL"
                lines.append(f"- **{criterion}**: {status}")
            lines.append("")

        lines.append("## Draft files")
        lines.append("")
        for i in range(1, len(drafts) + 1):
            lines.append(f"- `drafts/architect-pass-{i}.md`")
            lines.append(f"- `drafts/architect-pass-{i}-eval.json`")
        lines.append("")
        lines.append("## Best draft")
        lines.append("")
        best_i = max(range(1, len(drafts) + 1), key=lambda i: drafts[i - 1][1])
        lines.append(f"The best draft is `drafts/architect-pass-{best_i}.md`")
        lines.append("")

        escalation_path.write_text("\n".join(lines), encoding="utf-8")

    # -- helpers -------------------------------------------------------------

    def _format_failures(self, evaluation: dict[str, Any]) -> str:
        if "reason" in evaluation:
            return evaluation["reason"]

        lines = []
        for criterion in self.EVALUATION_CRITERIA:
            entry = evaluation.get(criterion, {})
            if not isinstance(entry, dict):
                continue
            if entry.get("score") == 0:
                issues = entry.get("issues", [])
                issue_text = "; ".join(issues) if issues else "no details provided"
                lines.append(f"FAILED: [{criterion.capitalize()}] — {issue_text}")
        return "\n".join(lines) if lines else "No specific feedback available."

    def _append_forum_context(self, prompt: str) -> str:
        forum_path = self.state.project_dir / "PERSONA_FORUM.md"
        if not forum_path.exists():
            return prompt
        forum = forum_path.read_text(encoding="utf-8", errors="replace").strip()
        if not forum:
            return prompt
        if len(forum) > 6000:
            forum = forum[:6000].rstrip() + "\n\n[persona forum truncated]"
        return (
            f"{prompt.rstrip()}\n\n"
            "Founding team forum context:\n\n"
            f"{forum}\n"
        )
