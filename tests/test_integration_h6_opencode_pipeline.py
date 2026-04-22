"""H6.6 end-to-end guardrail for the production opencode pipeline.

This test does not use ``--dry-run`` or in-memory SessionRunner doubles.
Instead it puts a fake ``opencode`` binary on PATH, runs the real CLI
config path, and lets ``orchestrator.cli.run`` build production
``OpencodeSession`` instances from an ``endpoints:`` block.

That covers the integration point H6 cares about:

    Config YAML -> opencode.json -> OpencodeSession subprocess ->
    role artifact writers -> raw-io.jsonl + usage.jsonl audit trail
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from orchestrator.cli.run import add_run_subparser, cmd_run
from orchestrator.lib.raw_io import raw_io_path
from orchestrator.lib.usage_writer import usage_path
from orchestrator.lib.workflow import default_workflow, save_workflow


_SPRINT_PLAN = (
    "# Sprint Plan (fake opencode)\n\n"
    "## Overview\n"
    "Fake opencode drives one bounded task through the full engine.\n\n"
    "## Memory Tiers\n"
    "- **Global Memory:** verify production subprocess wiring.\n"
    "- **Sprint Memory:** produce README.md and inspect it with a finite command.\n"
    "- **Task Packet Memory:** keep the run deterministic and local.\n\n"
    "## Traceability Matrix\n"
    "- `REQ-1` -> Task 1\n"
    "- `RISK-1` -> Task 1\n\n"
    "## Architecture Decisions\n"
    "- Use one static README artifact so validators can prove the coder ran.\n\n"
    "## Tasks\n\n"
    "### Task 1: bootstrap\n"
    "- **Priority**: P0\n"
    "- **Dependencies**: none\n"
    "- **Files**: `README.md`\n\n"
    "**Acceptance Criteria:**\n"
    "- [ ] README exists\n\n"
    "**Evidence Required:**\n"
    "- Run `ls README.md`\n\n"
    "**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)\n"
    "- [ ] README.md check pending\n\n"
    "**Implementation Notes:**\n"
    "Source Requirements: `REQ-1`, `RISK-1`\n"
    "Task Memory: Create README.md and keep verification bounded to a single ls command.\n"
    "Determinism Notes: Only README.md may change; verifier expects README.md to exist.\n\n"
    "## Risks & Mitigations\n"
    "1. None - fake opencode fixture only.\n"
)

_JUDGE_JSON = (
    '{"specificity":{"score":1,"issues":[]},'
    '"testability":{"score":1,"issues":[]},'
    '"evidence":{"score":1,"issues":[]},'
    '"completeness":{"score":1,"issues":[]},'
    '"feasibility":{"score":1,"issues":[]},'
    '"risk":{"score":1,"issues":[]}}'
)


def _install_fake_opencode(tmp_path: Path) -> Path:
    """Install a role-aware fake opencode binary and return its bin dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture_dir = tmp_path / "fake-opencode"
    fixture_dir.mkdir()
    exports_dir = fixture_dir / "exports"
    exports_dir.mkdir()
    log_path = fixture_dir / "calls.jsonl"

    shim_src = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import os
        import pathlib
        import sys

        EXPORTS_DIR = pathlib.Path({str(exports_dir)!r})
        LOG_PATH = pathlib.Path({str(log_path)!r})
        SPRINT_PLAN = {_SPRINT_PLAN!r}
        JUDGE_JSON = {_JUDGE_JSON!r}

        ROLE_TEXT = {{
            "architect": SPRINT_PLAN,
            "judge": JUDGE_JSON,
            "coder": "Wrote README.md.",
            "tester": "# Test Report\\n\\nTasks verified: 1\\n\\n### Task 1: bootstrap\\n- Status: VERIFIED\\n- Evidence 1: PASS - README.md\\n",
            "reviewer": "- [PASS] Criterion: README exists\\n  - Notes: verified by tester\\n\\n## Overall\\nAPPROVED\\n",
            "deployer": "# DEPLOY (fake opencode)\\n\\n1. Deployment target: local\\n2. Required env vars: none\\n3. Manual steps: none\\n4. Smoke-test commands: ls README.md\\n",
        }}

        def arg_after(argv, flag, default=None):
            if flag not in argv:
                return default
            idx = argv.index(flag)
            if idx + 1 >= len(argv):
                return default
            return argv[idx + 1]

        def append_log(record):
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\\n")

        def split_model(value):
            if "/" not in value:
                return value, ""
            provider, model = value.split("/", 1)
            return provider, model

        def assistant_message(role, provider, model, text, project_dir):
            parts = []
            if role == "coder":
                readme = pathlib.Path(project_dir) / "README.md"
                readme.write_text("# Fake opencode\\n", encoding="utf-8")
                parts.append({{
                    "type": "tool",
                    "tool": "write",
                    "state": {{
                        "status": "completed",
                        "input": {{
                            "filePath": str(readme),
                            "content": "# Fake opencode\\n",
                        }},
                        "output": "Wrote file successfully.",
                        "time": {{"start": 10, "end": 20}},
                    }},
                }})
            parts.append({{"type": "text", "text": text}})
            return {{
                "info": {{
                    "role": "assistant",
                    "model": {{"providerID": provider, "modelID": model}},
                    "tokens": {{
                        "total": 7,
                        "input": 5,
                        "output": 2,
                        "reasoning": 0,
                        "cache": {{"read": 0, "write": 0}},
                    }},
                    "cost": 0.001,
                    "time": {{"created": 1000, "completed": 1012}},
                }},
                "parts": parts,
            }}

        argv = sys.argv
        if len(argv) >= 2 and argv[1] == "run":
            role = arg_after(argv, "--agent", "unknown")
            project_dir = arg_after(argv, "--dir", os.getcwd())
            model_value = arg_after(argv, "--model", "fake/qwen")
            provider, model = split_model(model_value)
            prompt = argv[-1]
            session_index = len(list(EXPORTS_DIR.glob("*.json"))) + 1
            session_id = f"ses_{{role}}_{{session_index}}"
            text = ROLE_TEXT.get(role, f"ok from {{role}}")

            export = {{
                "info": {{
                    "id": session_id,
                    "directory": project_dir,
                    "summary": {{
                        "additions": 1 if role == "coder" else 0,
                        "deletions": 0,
                        "files": 1 if role == "coder" else 0,
                    }},
                }},
                "messages": [
                    assistant_message(role, provider, model, text, project_dir),
                ],
            }}
            (EXPORTS_DIR / f"{{session_id}}.json").write_text(
                json.dumps(export), encoding="utf-8"
            )
            append_log({{
                "kind": "run",
                "role": role,
                "session_id": session_id,
                "model": model_value,
                "config": os.environ.get("OPENCODE_CONFIG"),
                "autoupdate": os.environ.get("OPENCODE_DISABLE_AUTOUPDATE"),
                "prompt_contains": prompt[:80],
            }})
            print("fake opencode")
            print(json.dumps({{"type": "step_start", "sessionID": session_id}}))
            print(json.dumps({{"type": "text", "sessionID": session_id, "part": {{"type": "text", "text": text[:32]}}}}))
            print(json.dumps({{"type": "step_finish", "sessionID": session_id}}))
            sys.exit(0)

        if len(argv) >= 3 and argv[1] == "export":
            session_id = argv[2]
            append_log({{"kind": "export", "session_id": session_id}})
            print(f"Exporting session: {{session_id}}")
            sys.stdout.write((EXPORTS_DIR / f"{{session_id}}.json").read_text(encoding="utf-8"))
            sys.exit(0)

        sys.stderr.write(f"unexpected fake opencode argv: {{argv}}\\n")
        sys.exit(2)
        """
    )
    shim = bin_dir / "opencode"
    shim.write_text(shim_src, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _parse_run_args(config_path: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    add_run_subparser(sub)
    return parser.parse_args(["run", "--config", str(config_path), "--no-gates"])


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_fake_opencode_binary_drives_full_live_config_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "qwendea.md").write_text(
        "# Project\n\nBuild the smallest README-producing project.\n",
        encoding="utf-8",
    )
    workflow = default_workflow()
    if not any(step["id"] == "architect" for step in workflow):
        workflow.insert(
            0,
            {
                "id": "architect",
                "title": "Architect",
                "type": "phase",
                "handler": "architect",
                "enabled": True,
            },
        )
    enabled = {"architect", "implementation", "testing", "review", "deployment"}
    for step in workflow:
        step["enabled"] = step["id"] in enabled
    save_workflow(project_dir, workflow)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            f"""\
            llama_server_url: http://unused.invalid
            project_dir: {project_dir}
            require_human_approval: false
            max_retries: 1
            architect_max_passes: 1

            endpoints:
              - name: local-fake
                base_url: http://unused.invalid/v1
                model: qwen-fake

            routing:
              architect:
                - local-fake
              coder:
                - local-fake
              tester:
                - local-fake
              reviewer:
                - local-fake
              deployer:
                - local-fake
            """
        ),
        encoding="utf-8",
    )

    bin_dir = _install_fake_opencode(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    assert cmd_run(_parse_run_args(config_path)) == 0

    for artifact in ("sprint-plan.md", "README.md", "TEST_REPORT.md", "REVIEW.md", "DEPLOY.md"):
        assert (project_dir / artifact).exists(), f"{artifact} was not produced"

    calls = _read_jsonl(tmp_path / "fake-opencode" / "calls.jsonl")
    run_calls = [c for c in calls if c["kind"] == "run"]
    assert [c["role"] for c in run_calls] == [
        "architect",
        "judge",
        "coder",
        "tester",
        "reviewer",
        "deployer",
    ]
    assert all(c["model"] == "local-fake/qwen-fake" for c in run_calls)
    assert all(c["autoupdate"] == "1" for c in run_calls)
    assert all(
        c["config"] == str(project_dir / ".orchestrator" / "opencode" / "opencode.json")
        for c in run_calls
    )

    raw_records = _read_jsonl(raw_io_path(project_dir))
    usage_records = _read_jsonl(usage_path(project_dir))
    expected_roles = {"architect", "judge", "coder", "tester", "reviewer", "deployer"}
    assert expected_roles.issubset({r["role"] for r in raw_records})
    assert expected_roles.issubset({r["role"] for r in usage_records})
    assert {r["request_id"] for r in raw_records} == {u["call_id"] for u in usage_records}
    assert all(u["provider_kind"] == "opencode" for u in usage_records)
    assert {
        u["runtime"]["opencode"]["session_id"]
        for u in usage_records
    } == {c["session_id"] for c in run_calls}
