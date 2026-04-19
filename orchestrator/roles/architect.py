"""Architect role — produces sprint-plan.md from qwendea.md."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "architect"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ArchitectFailure(Exception):
    """Raised when the Architect exhausts all retry passes."""


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    """Load a prompt template from the architect prompts directory."""
    path = _PROMPT_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Architect
# ---------------------------------------------------------------------------


@dataclass
class Architect:
    """Generates and self-evaluates sprint plans."""

    llm: LLMClient
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
        """Run the self-eval loop. Returns path to sprint-plan.md on
        success. Raises ArchitectFailure on exhaustion."""
        qwendea = self.state.read_file("qwendea.md")

        best_plan: str | None = None
        best_score = 0
        best_eval: dict[str, Any] | None = None
        drafts: list[tuple[str, int, dict[str, Any]]] = []

        for pass_num in range(1, self.config.architect_max_passes + 1):
            if pass_num == 1:
                plan = self._generate(qwendea)
            else:
                plan = self._refine(qwendea, best_plan, best_eval)

            score, evaluation = self._self_evaluate(qwendea, plan)
            drafts.append((plan, score, evaluation))

            if self._passes(score, evaluation):
                self.state.write_file("sprint-plan.md", plan)
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

    # -- generation ----------------------------------------------------------

    def _generate(self, qwendea: str) -> str:
        """Generate an initial sprint plan from qwendea.md."""
        system_prompt = _load_prompt("generate")
        user_prompt = (
            f"Here is the project specification:\n\n"
            f"```\n{qwendea}\n```\n\n"
            f"Produce a sprint-plan.md following the structure specification."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        import time
        start = time.monotonic()
        try:
            response = self.llm.chat(messages, max_tokens=16384)
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_call
                log_llm_call(
                    self._phase_logger,
                    phase=self._phase,
                    role=self._role,
                    messages=messages,
                    response=response,
                    latency_ms=elapsed_ms,
                )
            return response.content
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_error
                log_llm_error(
                    self._phase_logger,
                    phase=self._phase,
                    role=self._role,
                    error=e,
                    latency_ms=elapsed_ms,
                )
            raise

    def _refine(self, qwendea: str, prior: str, prior_eval: dict[str, Any]) -> str:
        """Refine a sprint plan with targeted corrective feedback.

        Strips prior reasoning_content from the conversation history and
        injects only the failed-criteria feedback.
        """
        system_prompt = _load_prompt("generate")
        refine_template = _load_prompt("refine")

        # Build the failures description from the prior evaluation
        failures = self._format_failures(prior_eval)

        current_plan_text = f"Here is your previous sprint-plan.md:\n\n```\n{prior}\n```"
        failures_text = refine_template.format(failures=failures, current_plan=current_plan_text)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": failures_text},
        ]

        import time
        start = time.monotonic()
        try:
            response = self.llm.chat(messages, max_tokens=16384)
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_call
                log_llm_call(
                    self._phase_logger,
                    phase=self._phase,
                    role=self._role,
                    messages=messages,
                    response=response,
                    latency_ms=elapsed_ms,
                )
            return response.content
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_error
                log_llm_error(
                    self._phase_logger,
                    phase=self._phase,
                    role=self._role,
                    error=e,
                    latency_ms=elapsed_ms,
                )
            raise

    # -- self-evaluation -----------------------------------------------------

    def _self_evaluate(self, qwendea: str, plan: str) -> tuple[int, dict[str, Any]]:
        """Run the adversarial judge over qwendea.md + plan.

        Returns (score, evaluation_dict).
        Handles JSON parsing robustness: strict → re-prompt → regex fallback.
        """
        judge_prompt = _load_prompt("judge")

        user_prompt = (
            f"Here is the project specification:\n\n"
            f"```\n{qwendea}\n```\n\n"
            f"Here is the sprint plan to evaluate:\n\n"
            f"```\n{plan}\n```"
        )

        messages = [
            {"role": "system", "content": judge_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Try 1: strict parse
        raw = self._call_judge(messages)
        result = self._parse_json(raw)
        if result is not None:
            return self._compute_score(result)

        # Try 2: re-prompt with correction
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": "Your last output was not valid JSON. "
                       "Return only the JSON object, nothing else.",
        })
        raw = self._call_judge(messages)
        result = self._parse_json(raw)
        if result is not None:
            return self._compute_score(result)

        # Try 3: regex fallback
        result = self._extract_json_regex(raw)
        if result is not None:
            return self._compute_score(result)

        # Final failure: return score 0 with reason
        logger.warning("Architect self-eval: all JSON parsing attempts failed")
        return 0, {"reason": "malformed"}

    def _call_judge(self, messages: list[dict]) -> str:
        """Send the judge prompt and return raw response content."""
        import time
        start = time.monotonic()
        try:
            response = self.llm.chat(messages, max_tokens=4096)
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_call
                log_llm_call(
                    self._phase_logger,
                    phase=self._phase,
                    role="judge",
                    messages=messages,
                    response=response,
                    latency_ms=elapsed_ms,
                )
            return response.content
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_error
                log_llm_error(
                    self._phase_logger,
                    phase=self._phase,
                    role="judge",
                    error=e,
                    latency_ms=elapsed_ms,
                )
            raise

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        """Try strict JSON parse. Returns None on failure."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    @staticmethod
    def _extract_json_regex(raw: str) -> dict[str, Any] | None:
        """Extract the outermost {...} block from raw text."""
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    @staticmethod
    def _compute_score(evaluation: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Compute total score (0-6) from evaluation dict."""
        score = 0
        for criterion in ["specificity", "testability", "evidence",
                          "completeness", "feasibility", "risk"]:
            entry = evaluation.get(criterion, {})
            if isinstance(entry, dict) and entry.get("score") == 1:
                score += 1
        return score, evaluation

    # -- pass/fail logic -----------------------------------------------------

    def _passes(self, score: int, evaluation: dict[str, Any]) -> bool:
        """Check if the plan passes the evaluation rubric.

        Pass requires:
        - Score >= architect_pass_threshold
        - All MANDATORY criteria score 1
        """
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
        """Write escalation artifacts and prepare for human review."""
        drafts_dir = self.state.project_dir / ".orchestrator" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        # Write each draft
        for i, (plan, score, evaluation) in enumerate(drafts, start=1):
            plan_path = drafts_dir / f"architect-pass-{i}.md"
            plan_path.write_text(plan, encoding="utf-8")

            eval_path = drafts_dir / f"architect-pass-{i}-eval.json"
            eval_path.write_text(
                json.dumps(evaluation, indent=2), encoding="utf-8"
            )

        # Write human-readable escalation summary
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
        """Format failed criteria as human-readable feedback."""
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
