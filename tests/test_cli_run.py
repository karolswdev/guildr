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
    _build_opencode_session_runners,
    _load_config,
    add_run_subparser,
    cmd_run,
)
from orchestrator.lib.endpoints import load_endpoints


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


def test_live_runner_builder_includes_narrator(project: Path) -> None:
    cfg = load_endpoints(
        {
            "endpoints": [{"name": "local", "base_url": "http://127.0.0.1:8080", "model": "m"}],
            "routing": {"narrator": ["local"]},
        },
        env={},
    )
    assert cfg is not None

    runners = _build_opencode_session_runners(cfg, project)

    assert "narrator" in runners

