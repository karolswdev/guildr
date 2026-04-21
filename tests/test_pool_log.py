"""Unit tests for pool routing decision persistence."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.lib.pool_log import pool_log_path, write_decision


def test_write_decision_appends_expected_fields(tmp_path: Path) -> None:
    write_decision(
        tmp_path,
        call_id="abc123",
        role="coder",
        chosen_endpoint="primary",
        attempted_endpoints=["primary"],
        fell_back=False,
    )

    lines = pool_log_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["call_id"] == "abc123"
    assert record["role"] == "coder"
    assert record["chosen_endpoint"] == "primary"
    assert record["attempted_endpoints"] == ["primary"]
    assert record["fell_back"] is False
    assert "ts" in record


def test_write_decision_records_fallback(tmp_path: Path) -> None:
    write_decision(
        tmp_path,
        call_id="def456",
        role="reviewer",
        chosen_endpoint="alien",
        attempted_endpoints=["primary", "alien"],
        fell_back=True,
    )

    record = json.loads(pool_log_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])
    assert record["chosen_endpoint"] == "alien"
    assert record["attempted_endpoints"] == ["primary", "alien"]
    assert record["fell_back"] is True


def test_write_decision_noop_without_project_dir() -> None:
    write_decision(
        None,
        call_id="xyz",
        role="coder",
        chosen_endpoint="primary",
        attempted_endpoints=["primary"],
        fell_back=False,
    )  # must not raise


def test_write_decision_is_append_only(tmp_path: Path) -> None:
    for call_id in ("one", "two", "three"):
        write_decision(
            tmp_path,
            call_id=call_id,
            role="coder",
            chosen_endpoint="primary",
            attempted_endpoints=["primary"],
            fell_back=False,
        )

    ids = [
        json.loads(line)["call_id"]
        for line in pool_log_path(tmp_path).read_text(encoding="utf-8").splitlines()
    ]
    assert ids == ["one", "two", "three"]
