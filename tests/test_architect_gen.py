"""Tests for Architect._generate and Architect._refine (H6.3e: opencode runner)."""

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
            return _result("default response")
        return _result(self.responses.pop(0))


SAMPLE_PLAN = (
    "# Sprint Plan\n\n"
    "## Overview\nTest plan.\n\n"
    "## Architecture Decisions\n- Decision 1\n\n"
    "## Tasks\n\n"
    "### Task 1: Setup\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `setup.py`\n\n"
    "**Acceptance Criteria:**\n- [ ] Setup works\n\n"
    "**Evidence Required:**\n- Run `pytest tests/`\n\n"
    "**Evidence Log:**\n- [ ] Test command run\n\n"
    "## Risks & Mitigations\n1. Risk — Mitigation"
)


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


@pytest.fixture
def runner():
    return _FakeRunner(responses=[SAMPLE_PLAN])


@pytest.fixture
def judge_runner():
    return _FakeRunner()


@pytest.fixture
def architect(runner, judge_runner, state, config):
    return Architect(
        runner=runner,
        judge_runner=judge_runner,
        state=state,
        config=config,
    )


class TestGenerate:
    def test_generate_calls_runner_once(self, architect, runner):
        architect._generate("# Project: Test\n\n## Description\nA test project.")
        assert len(runner.prompts) == 1

    def test_generate_prompt_includes_qwendea(self, architect, runner):
        architect._generate("# Project: Foo\n\n## Description\nBar.")
        assert "Foo" in runner.prompts[0]
        assert "Bar" in runner.prompts[0]

    def test_generate_returns_markdown(self, architect):
        response = architect._generate("# Project: Test\n\n## Description\nTest.")
        assert "# Sprint Plan" in response
        assert "## Tasks" in response

    def test_generate_prompt_requires_automated_evidence(self, architect, runner):
        architect._generate("# Project: Test\n\n## Description\nTest.")
        prompt = runner.prompts[0]
        assert "automated verification command" in prompt
        assert "finite" in prompt
        assert "npm run dev" in prompt
        assert "MUST NOT be" in prompt


class TestRefine:
    def _eval_with_testability_fail(self):
        return {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["Task 1: 'Works' is not verifiable"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

    def test_refine_injects_only_failed_criteria(self, architect, runner):
        prior = SAMPLE_PLAN
        architect._refine("# Project: Test", prior, self._eval_with_testability_fail())
        prompt = runner.prompts[0]
        assert "testability" in prompt.lower()
        assert "not verifiable" in prompt
        assert '"specificity"' not in prompt
        assert '"completeness"' not in prompt

    def test_refine_includes_prior_plan(self, architect, runner):
        prior = SAMPLE_PLAN
        architect._refine("# Project: Test", prior, self._eval_with_testability_fail())
        assert "# Sprint Plan" in runner.prompts[0]
        assert "Task 1: Setup" in runner.prompts[0]
