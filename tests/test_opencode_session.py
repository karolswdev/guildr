"""Coverage for the OpencodeSession subprocess adapter (H6.2).

Two layers:

1. Pure parsing (:func:`parse_export`) — fed canned export JSON, no
   subprocess. Fast, deterministic, guards the data-extraction contract
   against opencode schema drift.
2. End-to-end via a **fake opencode binary** — a tiny Python shim on
   ``PATH`` that mimics ``opencode run --format json`` (NDJSON on
   stdout) and ``opencode export <sid>`` (banner + canonical JSON).
   Guards the argv shape, env plumbing, stdout streaming, and export
   invocation without requiring the real opencode to be installed in CI.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from orchestrator.lib.opencode import (
    OpencodeBinaryMissing,
    OpencodeError,
    OpencodeSession,
    OpencodeTokens,
    parse_export,
)


# ---------------------------------------------------------------------------
# Fixture data — one canonical export + matching event stream.
# ---------------------------------------------------------------------------


def _canned_export() -> dict:
    return {
        "info": {
            "id": "ses_fake123",
            "directory": "/fake/project",
            "summary": {"additions": 4, "deletions": 1, "files": 2},
            "time": {"created": 1, "updated": 2},
        },
        "messages": [
            {
                "info": {
                    "role": "user",
                    "id": "msg_u",
                    "model": {"providerID": "local-gpu", "modelID": "qwen:30b"},
                },
                "parts": [{"type": "text", "text": "do the thing"}],
            },
            {
                "info": {
                    "role": "assistant",
                    "id": "msg_a",
                    "model": {"providerID": "local-gpu", "modelID": "qwen:30b"},
                    "tokens": {
                        "total": 120, "input": 100, "output": 20,
                        "reasoning": 0, "cache": {"read": 5, "write": 3},
                    },
                    "cost": 0.0,
                },
                "parts": [
                    {
                        "type": "tool",
                        "tool": "write",
                        "state": {
                            "status": "completed",
                            "input": {"filePath": "/fake/project/out.txt",
                                      "content": "HELLO"},
                            "output": "Wrote file successfully.",
                            "time": {"start": 10, "end": 20},
                        },
                    },
                    {"type": "text", "text": "Done."},
                ],
            },
        ],
    }


def _canned_events(session_id: str) -> list[dict]:
    return [
        {"type": "step_start", "sessionID": session_id,
         "part": {"type": "step-start"}},
        {"type": "text", "sessionID": session_id,
         "part": {"type": "text", "text": "Done."}},
        {"type": "step_finish", "sessionID": session_id,
         "part": {"type": "step-finish", "reason": "stop"}},
    ]


# ---------------------------------------------------------------------------
# Pure parsing tests.
# ---------------------------------------------------------------------------


def test_parse_export_extracts_messages_tokens_and_summary() -> None:
    messages, totals, cost, summary = parse_export(_canned_export())
    assert [m.role for m in messages] == ["user", "assistant"]
    assistant = messages[1]
    assert assistant.provider == "local-gpu"
    assert assistant.model == "qwen:30b"
    assert assistant.text_parts == ["Done."]
    assert len(assistant.tool_calls) == 1
    assert assistant.tool_calls[0].tool == "write"
    assert assistant.tool_calls[0].status == "completed"
    assert assistant.tool_calls[0].input["content"] == "HELLO"
    assert totals == OpencodeTokens(
        total=120, input=100, output=20, cache_read=5, cache_write=3
    )
    assert cost == 0.0
    assert summary == {"additions": 4, "deletions": 1, "files": 2}


def test_parse_export_handles_missing_optional_fields() -> None:
    """A minimal export (no summary, no tokens) must not crash."""
    minimal = {
        "info": {"id": "ses_x", "directory": "/x"},
        "messages": [
            {"info": {"role": "assistant", "id": "m"}, "parts": []},
        ],
    }
    messages, totals, cost, summary = parse_export(minimal)
    assert len(messages) == 1
    assert messages[0].tokens == OpencodeTokens()
    assert totals == OpencodeTokens()
    assert cost == 0.0
    assert summary == {"additions": 0, "deletions": 0, "files": 0}


# ---------------------------------------------------------------------------
# Subprocess tests via fake-opencode shim on PATH.
# ---------------------------------------------------------------------------


def _install_fake_opencode(
    tmp_path: Path,
    events: list[dict],
    export: dict,
    session_id: str,
    *,
    run_exit: int = 0,
) -> Path:
    """Drop a Python shim at ``<tmp_path>/bin/opencode`` and return its dir.

    The shim dispatches on argv[1] (``run`` / ``export``). On ``run``
    it emits each event as one NDJSON line, prints a non-JSON banner
    (we rely on the adapter to skip those), and exits ``run_exit``.
    On ``export <sid>`` it emits the banner + canonical JSON.
    Also writes argv + OPENCODE_CONFIG out to ``<tmp_path>/run.json``
    so tests can assert on invocation shape.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    events_file = fixtures_dir / "events.ndjson"
    events_file.write_text(
        "\n".join(json.dumps(ev) for ev in events) + "\n", encoding="utf-8"
    )
    export_file = fixtures_dir / "export.json"
    export_file.write_text(json.dumps(export), encoding="utf-8")
    run_log = tmp_path / "run.json"

    shim_src = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json, os, sys
        argv = sys.argv
        log_path = {str(run_log)!r}
        # Append each invocation so tests can assert on argv + env.
        record = {{
            "argv": argv,
            "config": os.environ.get("OPENCODE_CONFIG"),
            "autoupdate": os.environ.get("OPENCODE_DISABLE_AUTOUPDATE"),
        }}
        existing = []
        if os.path.exists(log_path):
            with open(log_path) as f:
                existing = json.load(f)
        existing.append(record)
        with open(log_path, "w") as f:
            json.dump(existing, f)

        if len(argv) >= 2 and argv[1] == "run":
            # Banner — non-JSON line that the adapter must skip.
            print("opencode 1.14.20 — fake shim")
            with open({str(events_file)!r}) as f:
                sys.stdout.write(f.read())
            sys.stdout.flush()
            sys.exit({run_exit})
        if len(argv) >= 3 and argv[1] == "export":
            sid = argv[2]
            print(f"Exporting session: {{sid}}")
            with open({str(export_file)!r}) as f:
                sys.stdout.write(f.read())
            sys.stdout.flush()
            sys.exit(0)
        sys.stderr.write(f"fake opencode got unexpected argv: {{argv}}\\n")
        sys.exit(2)
        """
    )
    shim = bin_dir / "opencode"
    shim.write_text(shim_src, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


@pytest.fixture
def fake_opencode_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Returns (session, run_log_path) with opencode shim on PATH."""
    session_id = "ses_fake123"
    events = _canned_events(session_id)
    export = _canned_export()
    bin_dir = _install_fake_opencode(tmp_path, events, export, session_id)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    config_path = tmp_path / "opencode.json"
    config_path.write_text("{}", encoding="utf-8")
    session = OpencodeSession(
        project_dir=tmp_path / "project",
        config_path=config_path,
        provider="local-gpu",
        model="qwen:30b",
        agent="coder",
    )
    return session, tmp_path / "run.json"


def test_run_returns_parsed_result_from_fake_shim(fake_opencode_session) -> None:
    session, _ = fake_opencode_session
    result = session.run("do the thing")
    assert result.session_id == "ses_fake123"
    assert result.exit_code == 0
    assert result.directory == "/fake/project"
    assert result.total_tokens.total == 120
    assert result.summary_additions == 4
    assert result.summary_files == 2
    assert result.assistant_text == "Done."
    assert [t.tool for t in result.tool_calls] == ["write"]
    # NDJSON events were captured verbatim for debugging.
    assert [ev["type"] for ev in result.raw_events] == [
        "step_start", "text", "step_finish"
    ]


def test_run_forwards_every_event_to_sink(fake_opencode_session) -> None:
    session, _ = fake_opencode_session
    received: list[dict] = []
    session.event_sink = received.append
    session.run("hi")
    assert [ev["type"] for ev in received] == [
        "step_start", "text", "step_finish"
    ]


def test_run_invocation_shape_and_env(fake_opencode_session) -> None:
    """argv must include --format json, --dir, --model p/m, --agent, and
    the config path must flow through OPENCODE_CONFIG."""
    session, log_path = fake_opencode_session
    session.run("hi")
    calls = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(calls) == 2  # one run, one export
    run_call = calls[0]
    argv = run_call["argv"]
    assert argv[1] == "run"
    assert "--format" in argv and argv[argv.index("--format") + 1] == "json"
    assert "--dir" in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "local-gpu/qwen:30b"
    assert argv[argv.index("--agent") + 1] == "coder"
    assert "--dangerously-skip-permissions" in argv
    assert argv[-1] == "hi"
    assert run_call["config"] == str(session.config_path)
    assert run_call["autoupdate"] == "1"
    export_call = calls[1]
    assert export_call["argv"][1:] == ["export", "ses_fake123"]


def test_run_raises_when_binary_missing(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir, no opencode
    session = OpencodeSession(
        project_dir=tmp_path,
        config_path=tmp_path / "opencode.json",
        provider="p",
        model="m",
    )
    with pytest.raises(OpencodeBinaryMissing):
        session.run("hi")


def test_run_raises_when_no_session_id_emitted(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """If opencode exits without ever emitting a sessionID we have
    nothing to export — surface as OpencodeError, not a partial result."""
    bin_dir = _install_fake_opencode(
        tmp_path, events=[], export=_canned_export(),
        session_id="ses_fake123", run_exit=1,
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    config_path = tmp_path / "opencode.json"
    config_path.write_text("{}", encoding="utf-8")
    session = OpencodeSession(
        project_dir=tmp_path / "project",
        config_path=config_path,
        provider="local-gpu",
        model="qwen:30b",
    )
    with pytest.raises(OpencodeError, match="no sessionID"):
        session.run("hi")


def test_run_passes_continue_session_id(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "ses_fake123"
    bin_dir = _install_fake_opencode(
        tmp_path, _canned_events(session_id), _canned_export(), session_id,
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    config_path = tmp_path / "opencode.json"
    config_path.write_text("{}", encoding="utf-8")
    session = OpencodeSession(
        project_dir=tmp_path / "project",
        config_path=config_path,
        provider="local-gpu",
        model="qwen:30b",
    )
    session.run("hi", continue_session_id="ses_prev")
    calls = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    argv = calls[0]["argv"]
    assert argv[argv.index("--session") + 1] == "ses_prev"
