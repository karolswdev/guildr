"""Tests for MemPalace wrapper provenance and scrubbing."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from orchestrator.lib.memory_palace import memory_provenance, search_memory


def test_memory_provenance_is_compact_and_hashes_wakeup(tmp_path: Path) -> None:
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "wake-up.md").write_text("wake up", encoding="utf-8")

    with patch("orchestrator.lib.memory_palace.resolve_command", return_value=["mempalace"]):
        packet = memory_provenance("project-1", tmp_path)

    assert packet == {
        "project_id": "project-1",
        "available": True,
        "initialized": False,
        "wing": "project-1",
        "wake_up_hash": hashlib.sha256(b"wake up").hexdigest(),
        "wake_up_bytes": len("wake up"),
        "memory_refs": [".orchestrator/memory/wake-up.md"],
        "artifact_refs": [".orchestrator/memory/wake-up.md"],
    }


def test_search_memory_scrubs_query_and_cached_output(tmp_path: Path) -> None:
    with (
        patch("orchestrator.lib.memory_palace.resolve_command", return_value=["mempalace"]),
        patch(
            "orchestrator.lib.memory_palace._run",
            return_value="Found Authorization: Bearer secret-token and sk-live-secret-token",
        ) as run_mock,
    ):
        result = search_memory(
            "project-1",
            tmp_path,
            query="api_key=sk-live-secret-value",
            results=3,
        )

    assert run_mock.call_args.args[1] == [
        "search",
        "api_key=[redacted]",
        "--wing",
        "project-1",
        "--results",
        "3",
    ]
    assert result["query"] == "api_key=[redacted]"
    assert "secret-token" not in result["output"]
    cached = (tmp_path / ".orchestrator" / "memory" / "last-search.txt").read_text(encoding="utf-8")
    assert "secret-token" not in cached
    assert "[redacted]" in cached
