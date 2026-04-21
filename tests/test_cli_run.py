"""Smoke tests for the `orchestrate run` CLI entrypoint.

This is the surface a human (or shell harness) actually invokes, so
regressions in argparse wiring or dry-run dispatch should fail loudly
here rather than at the next manual run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from orchestrator.cli.run import (
    _build_dry_run_llm,
    _load_config,
    add_run_subparser,
    cmd_run,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    (pd / "qwendea.md").write_text("# Project\n\nTrivial.\n")
    return pd


def _make_args(project: Path, **overrides: object) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    add_run_subparser(sub)
    args = parser.parse_args([
        "run", "--from-env", "--dry-run", "--no-gates",
        "--project", str(project),
    ])
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def test_argparse_wiring(project: Path) -> None:
    args = _make_args(project)
    assert args.dry_run is True
    assert args.no_gates is True
    assert args.project == project


def test_gate_flag_forces_require_human_approval_true(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--gate` opts into attended mode even when Config defaults would drift."""
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://x")
    monkeypatch.setenv("PROJECT_DIR", str(project))
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    add_run_subparser(sub)
    args = parser.parse_args(
        ["run", "--from-env", "--dry-run", "--gate", "--project", str(project)]
    )
    cfg = _load_config(args)
    assert cfg.require_human_approval is True


def test_gate_and_no_gates_are_mutually_exclusive(project: Path) -> None:
    """Can't ask for attended-and-unattended in the same run."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    add_run_subparser(sub)
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["run", "--from-env", "--dry-run", "--gate", "--no-gates",
             "--project", str(project)]
        )


def test_load_config_applies_overrides(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://x")
    monkeypatch.setenv("PROJECT_DIR", str(project))
    args = _make_args(project)
    cfg = _load_config(args)
    assert cfg.project_dir == project
    assert cfg.require_human_approval is False


def test_load_config_allows_dry_run_without_llama_url(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLAMA_SERVER_URL", raising=False)
    monkeypatch.delenv("LLAMA_URL", raising=False)
    monkeypatch.delenv("LLAMA_PRIMARY_URL", raising=False)
    monkeypatch.setenv("PROJECT_DIR", str(project))
    args = _make_args(project)
    cfg = _load_config(args)
    assert cfg.project_dir == project
    assert cfg.llama_server_url == "http://dry-run.invalid"


def test_cmd_run_dry_run_succeeds(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://unused")
    monkeypatch.setenv("PROJECT_DIR", str(project))
    args = _make_args(project)
    rc = cmd_run(args)
    assert rc == 0
    assert (project / "sprint-plan.md").exists()
    assert (project / "DEPLOY.md").exists()


def test_dry_run_llm_dispatches_by_role() -> None:
    """Regression guard: each role gets its own canned response shape."""
    fake = _build_dry_run_llm()

    architect = fake.chat([{"role": "system", "content": "You are a senior software architect."}])
    assert "Evidence Required:" in architect.content

    judge = fake.chat([
        {"role": "system", "content": "You are a skeptical senior engineering manager."}
    ])
    assert '"specificity"' in judge.content

    # Coder no longer goes through fake_llm — it's driven by a SessionRunner
    # (see orchestrator/roles/coder_dryrun.py). Only the remaining LLM roles
    # still ride this dispatch.

    tester = fake.chat([{"role": "system", "content": "You are a QA engineer."}])
    assert "VERIFIED" in tester.content

    # Reviewer / Deployer no longer go through fake_llm — they're driven by
    # SessionRunners (see reviewer_dryrun.py / deployer_dryrun.py) after
    # H6.3c / H6.3d.
