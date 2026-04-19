"""End-to-end integration test: drives the orchestrator through every
phase using FakeLLMClient and asserts the expected artifacts land.

This is the cross-phase wiring check that the per-module unit tests
don't provide. If you change phase ordering, role contracts, or which
files each role writes, expect this test to fail loudly — that is the
point.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.cli.run import _build_dry_run_llm
from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    (pd / "qwendea.md").write_text(
        "# Project: Tiny CLI\n\nBuild a one-command CLI that prints hello.\n"
    )
    return pd


@pytest.fixture
def config(project_dir: Path) -> Config:
    return Config(
        llama_server_url="http://unused-in-dry-run",
        project_dir=project_dir,
        require_human_approval=False,
        max_retries=2,
        architect_max_passes=2,
    )


def test_dry_run_pipeline_produces_expected_artifacts(
    config: Config, project_dir: Path
) -> None:
    """Run the full pipeline in dry-run; assert each phase wrote its file."""
    fake = _build_dry_run_llm()

    orchestrator = Orchestrator(config=config, fake_llm=fake)
    orchestrator.run()

    sprint_plan = project_dir / "sprint-plan.md"
    assert sprint_plan.exists(), "architect did not write sprint-plan.md"
    plan_text = sprint_plan.read_text()
    assert "Evidence Required:" in plan_text, (
        "architect wrote sprint-plan.md but it does not look like a real plan "
        f"(content: {plan_text!r})"
    )
    assert plan_text != "sprint-plan.md", (
        "regression: engine overwrote sprint-plan.md with the path string "
        "(see Architect.execute return value vs engine._architect)"
    )

    for required in ("TEST_REPORT.md", "REVIEW.md", "DEPLOY.md"):
        assert (project_dir / required).exists(), (
            f"{required} was not produced — phase wiring is broken"
        )

    assert fake.call_count > 0, "FakeLLMClient was never called"


def test_dry_run_pipeline_state_advanced_through_all_phases(
    config: Config, project_dir: Path
) -> None:
    """State should record the final phase reached, not crash mid-way."""
    fake = _build_dry_run_llm()
    orchestrator = Orchestrator(config=config, fake_llm=fake)
    orchestrator.run()

    state_file = project_dir / ".orchestrator" / "state.json"
    assert state_file.exists(), "orchestrator never wrote state.json"
    contents = state_file.read_text()
    assert "deployment" in contents, (
        "state.json never recorded the deployment phase — pipeline halted early"
    )
