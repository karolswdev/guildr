"""Tests for Architect._self_evaluate with JSON robustness (H6.3e)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect


PROMPT_DIR = Path(__file__).resolve().parent.parent / "orchestrator" / "roles" / "prompts" / "architect"

MIN_TRACEABLE_PLAN = (
    "# Sprint Plan\n\n"
    "## Overview\n"
    "Build the minimal slice with explicit traceability.\n\n"
    "## Memory Tiers\n"
    "- **Global Memory:** preserve the user outcome and bounded evidence.\n"
    "- **Sprint Memory:** keep the work centered on one task and one file.\n"
    "- **Task Packet Memory:** remember the file, command, and expected outcome.\n\n"
    "## Traceability Matrix\n"
    "- `REQ-1` -> Task 1\n"
    "- `RISK-1` -> Task 1\n\n"
    "## Tasks\n\n"
    "### Task 1: Test\n"
    "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n"
    "**Acceptance Criteria:**\n- [ ] Works\n\n"
    "**Evidence Required:**\n- Run `pytest`\n\n"
    "**Evidence Log:**\n- [ ] Done\n\n"
    "**Implementation Notes:**\n"
    "Source Requirements: `REQ-1`, `RISK-1`\n"
    "Task Memory: Keep the task isolated and verifier-safe.\n"
    "Determinism Notes: `test.py` is the only mutable file and `pytest` is the deciding evidence.\n\n"
    "## Risks & Mitigations\n1. Risk — Mitigation\n"
)


def _result(text: str, *, exit_code: int = 0) -> OpencodeResult:
    message = OpencodeMessage(
        role="assistant",
        provider="fake",
        model="fake",
        tokens=OpencodeTokens(total=1, input=1, output=0),
        cost=0.0,
        text_parts=[text],
        tool_calls=[],
    )
    return OpencodeResult(
        session_id="ses_test",
        exit_code=exit_code,
        directory=".",
        messages=[message] if text else [],
        total_tokens=message.tokens,
        total_cost=0.0,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


@dataclass
class _FakeRunner:
    responses: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def run(self, prompt: str) -> OpencodeResult:
        self.prompts.append(prompt)
        if not self.responses:
            return _result("default")
        return _result(self.responses.pop(0))


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


@pytest.fixture
def config(tmp_path):
    return Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=Path(tmp_path),
        architect_max_passes=3,
        architect_pass_threshold=4,
    )


def _make_architect(state, config, judge_responses):
    runner = _FakeRunner()
    judge_runner = _FakeRunner(responses=list(judge_responses))
    arch = Architect(
        runner=runner,
        judge_runner=judge_runner,
        state=state,
        config=config,
    )
    return arch, runner, judge_runner


class TestStrictJsonParse:
    def test_parses_valid_json(self):
        raw = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}'
        result = Architect._parse_json(raw)
        assert result is not None
        assert result["specificity"]["score"] == 1

    def test_rejects_non_dict_json(self):
        assert Architect._parse_json('[1, 2, 3]') is None

    def test_rejects_invalid_json(self):
        assert Architect._parse_json('not json') is None

    def test_rejects_empty_string(self):
        assert Architect._parse_json('') is None


def test_judge_rubric_allows_future_filled_placeholders():
    prompt = (PROMPT_DIR / "judge.txt").read_text(encoding="utf-8")
    assert "Evidence Required" in prompt
    assert "Do NOT fail" in prompt
    assert "<actual output>" in prompt
    assert "<short-sha>" in prompt


def test_judge_rubric_rejects_dev_server_evidence():
    prompt = (PROMPT_DIR / "judge.txt").read_text(encoding="utf-8")
    assert "long-running dev-server" in prompt
    assert "npm run dev" in prompt
    assert "observe" in prompt


def test_local_plan_checks_fail_interactive_evidence(state, config):
    good_json = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}'
    arch, _, _ = _make_architect(state, config, [good_json])
    plan = (
        MIN_TRACEABLE_PLAN
        .replace("Task 1: Test", "Task 1: Frontend")
        .replace("`test.py`", "`package.json`")
        .replace("Run `pytest`", "Run `npm run dev` and observe the browser.")
    )
    score, evaluation = arch._self_evaluate("# Project: Test", plan)
    assert score == 5
    assert evaluation["evidence"]["score"] == 0
    assert "long-running dev-server" in " ".join(evaluation["evidence"]["issues"])


class TestReprompt:
    def test_reprompt_on_prose_wrapper(self, state, config):
        prose_wrapped = 'Here is my evaluation:\n```json\n{"specificity": {"score": 1, "issues": []}, "testability": {"score": 0, "issues": ["vague"]}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}\n```'
        clean = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 0, "issues": ["vague"]}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}'
        arch, _, judge = _make_architect(state, config, [prose_wrapped, clean])
        score, evaluation = arch._self_evaluate("# Project: Test", MIN_TRACEABLE_PLAN)
        assert score == 5
        assert evaluation["testability"]["score"] == 0
        assert len(judge.prompts) == 2

    def test_reprompt_on_trailing_junk(self, state, config):
        trail = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}\n\nHope this helps!'
        clean = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}'
        arch, _, judge = _make_architect(state, config, [trail, clean])
        score, evaluation = arch._self_evaluate("# Project: Test", MIN_TRACEABLE_PLAN)
        assert score == 6
        assert len(judge.prompts) == 2


class TestRegexFallback:
    def test_extracts_outermost_json(self):
        raw = 'Some prose {\n  "specificity": {"score": 1, "issues": []},\n  "testability": {"score": 0, "issues": ["vague"]},\n  "evidence": {"score": 1, "issues": []},\n  "completeness": {"score": 1, "issues": []},\n  "feasibility": {"score": 1, "issues": []},\n  "risk": {"score": 1, "issues": []}\n} after'
        result = Architect._extract_json_regex(raw)
        assert result is not None
        assert result["testability"]["score"] == 0

    def test_fails_on_no_braces(self):
        assert Architect._extract_json_regex('no braces at all') is None

    def test_fails_on_invalid_inside_braces(self):
        assert Architect._extract_json_regex('{not valid json}') is None


class TestMalformedExhaustion:
    def test_returns_score_0_on_exhaustion(self, state, config):
        arch, _, judge = _make_architect(
            state, config, ["completely not json", "still not json"]
        )
        score, evaluation = arch._self_evaluate("# Project: Test", MIN_TRACEABLE_PLAN)
        assert score == 0
        assert evaluation == {"reason": "malformed"}
        assert len(judge.prompts) == 2

    def test_reprompt_message_is_injected(self, state, config):
        good = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}'
        arch, _, judge = _make_architect(state, config, ["{broken json", good])
        arch._self_evaluate("# Project: Test", MIN_TRACEABLE_PLAN)
        assert "not valid JSON" in judge.prompts[1]


class TestComputeScore:
    def test_score_6_all_pass(self):
        evaluation = {c: {"score": 1, "issues": []} for c in
                      ["specificity", "testability", "evidence",
                       "completeness", "feasibility", "risk"]}
        score, _ = Architect._compute_score(evaluation)
        assert score == 6

    def test_score_0_all_fail(self):
        evaluation = {c: {"score": 0, "issues": ["bad"]} for c in
                      ["specificity", "testability", "evidence",
                       "completeness", "feasibility", "risk"]}
        score, _ = Architect._compute_score(evaluation)
        assert score == 0

    def test_score_partial(self):
        evaluation = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["bad"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 0, "issues": ["bad"]},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 0, "issues": ["bad"]},
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 3

    def test_missing_treated_as_fail(self):
        evaluation = {"specificity": {"score": 1, "issues": []}}
        score, _ = Architect._compute_score(evaluation)
        assert score == 1

    def test_non_dict_treated_as_fail(self):
        evaluation = {
            "specificity": "not a dict",
            "testability": 42,
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 4
