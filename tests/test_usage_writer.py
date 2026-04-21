"""Unit tests for usage event persistence."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.lib.usage_writer import usage_path, write_usage


def test_write_usage_appends_json_line(tmp_path: Path) -> None:
    payload = {
        "call_id": "abc123",
        "provider_kind": "fake",
        "role": "coder",
        "usage": {"input_tokens": 12, "output_tokens": 34, "reasoning_tokens": 5},
        "cost_usd": 0.0,
    }

    write_usage(tmp_path, payload)

    path = usage_path(tmp_path)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == payload


def test_write_usage_is_append_only(tmp_path: Path) -> None:
    write_usage(tmp_path, {"call_id": "first"})
    write_usage(tmp_path, {"call_id": "second"})

    lines = usage_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["call_id"] for line in lines] == ["first", "second"]


def test_write_usage_noop_without_project_dir() -> None:
    # Does not raise — emit sites without a project_dir (e.g. ingestion
    # quiz) should still work.
    write_usage(None, {"call_id": "xyz"})


def test_write_usage_creates_parent_dir(tmp_path: Path) -> None:
    project_dir = tmp_path / "fresh"
    write_usage(project_dir, {"call_id": "one"})
    assert usage_path(project_dir).exists()
