# Getting Started

This guide starts with the safest path: a deterministic dry run that needs no
model server. After that, it shows how to run the same orchestration engine
against live opencode providers and how to inspect the PWA follow/replay
surface.

## Fast Smoke Test

Copy this first code block into a file such as `/tmp/guildr-docs-smoke.py` and
run it from the repository root with `.venv/bin/python /tmp/guildr-docs-smoke.py`.

```python
from pathlib import Path
from shutil import rmtree

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config

project_dir = Path("/tmp/guildr-docs-smoke")
rmtree(project_dir, ignore_errors=True)
project_dir.mkdir(parents=True)
(project_dir / "qwendea.md").write_text(
    "# Demo\n\nBuild a tiny README project with verifiable output.\n",
    encoding="utf-8",
)

config = Config(
    llama_server_url="http://dry-run.invalid",
    project_dir=project_dir,
    require_human_approval=False,
)
Orchestrator(config=config, dry_run=True).run()

expected = [
    "sprint-plan.md",
    "README.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "DEPLOY.md",
]
missing = [name for name in expected if not (project_dir / name).exists()]
if missing:
    raise SystemExit(f"missing artifacts: {missing}")
print("dry-run smoke passed")
```

Dry-run mode exercises the workflow, gates-off path, event ledger, audit rows,
next-step packets, deterministic role outputs, narrative digest emission, and
artifact writes. It does not contact opencode or a model provider.

## Prerequisites

1. Python 3.12+ with the project virtualenv installed.
2. Git available on `PATH`.
3. For live runs only: the `opencode` binary available on `PATH`.
4. For live runs only: at least one OpenAI-compatible model endpoint declared
   in `config.yaml`.

## Create A Project

The orchestrator expects a project directory containing `qwendea.md`, the
operator-authored source of truth.

```bash
export PROJECT_DIR=/tmp/fizzbuzz-project
rm -rf "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cat > "$PROJECT_DIR/qwendea.md" <<'EOF'
# Project: FizzBuzz CLI

## Description
A command-line FizzBuzz implementation that prints numbers 1-100, replacing
multiples of 3 with "Fizz", multiples of 5 with "Buzz", and multiples of both
with "FizzBuzz".

## Core Requirements
1. Accept optional --start and --end arguments.
2. Print one result per line to stdout.
3. Exit code 0 on success.

## Constraints
- Python 3.12+
- No external dependencies
EOF
```

## Dry Run From The CLI

Use dry-run mode to rehearse the pipeline from the terminal. `--no-gates`
keeps the run unattended.

```bash
export PROJECT_DIR=/tmp/fizzbuzz-project
.venv/bin/guildr run --from-env --dry-run --no-gates --project "$PROJECT_DIR"
```

Expected top-level artifacts:

- `sprint-plan.md`
- `README.md` or other implementation files
- `TEST_REPORT.md`
- `REVIEW.md`
- `DEPLOY.md`
- `.orchestrator/events/events.jsonl`
- `.orchestrator/logs/raw-io.jsonl`
- `.orchestrator/logs/usage.jsonl`
- `.orchestrator/narrative/digests/`
- `.orchestrator/discussion/`

## Live Run With Providers

Live runs use opencode sessions. Define providers and per-role routing in a
YAML config:

```yaml
llama_server_url: http://dry-run.invalid
project_dir: /tmp/fizzbuzz-project
require_human_approval: false

endpoints:
  - name: local-gpu
    base_url: http://127.0.0.1:8080/v1
    model: qwen3-coder:30b
  - name: openrouter
    base_url: https://openrouter.ai/api/v1
    model: anthropic/claude-3.5-haiku
    api_key_env: OPENROUTER_API_KEY

routing:
  architect:
    - endpoint: local-gpu
  judge:
    - endpoint: openrouter
  coder:
    - endpoint: local-gpu
  tester:
    - endpoint: local-gpu
  reviewer:
    - endpoint: openrouter
  narrator:
    - endpoint: openrouter
  deployer:
    - endpoint: local-gpu
```

Then run:

```bash
export OPENROUTER_API_KEY=...
.venv/bin/guildr run --config config.yaml --no-gates
```

Use `--gate` instead of `--no-gates` for an attended run. The engine pauses at
human approval gates; the PWA can show and decide those gates when the run is
started through the backend runner.

## Use The PWA

Start the backend using the existing project scripts or test harness for your
environment, then open the LAN-only PWA. The operator-facing surfaces are:

- **Map:** live workflow atoms and current run state.
- **Next-Step Sheet:** what the engine plans to do next, why now, what inputs
  and memory refs it will use, and which operator intents are queued.
- **Object Lens:** the selected workflow object, artifact refs, source refs,
  story rows, and related intents.
- **Story Lens:** replay-folded narrative digests and discussion highlights.
- **Goal Core:** project purpose, founding-team context, current progress, and
  source refs.
- **Narrator dialogue:** neutral project synthesis rendered in the map surface.
- **Compose dock:** interject, intercept, reroute, or note intents that become
  durable event-ledger facts.

## Inspect Results

The inspect command reads the project artifacts and logs:

```bash
.venv/bin/guildr inspect "$PROJECT_DIR"
.venv/bin/guildr inspect "$PROJECT_DIR" --tokens
.venv/bin/guildr inspect "$PROJECT_DIR" --phase architect
```

For manual inspection, start with these files:

- `.orchestrator/events/events.jsonl`
- `.orchestrator/logs/raw-io.jsonl`
- `.orchestrator/logs/usage.jsonl`
- `.orchestrator/control/intents.jsonl`
- `.orchestrator/narrative/digests/*.json`
- `.orchestrator/discussion/log.jsonl`
- `.orchestrator/memory/wake-up.md` when MemPalace sync is enabled

## Next Steps

- Read [architecture.md](./architecture.md) for the current engine map.
- Read [pwa-narrative-replay-and-intervention-design.md](./pwa-narrative-replay-and-intervention-design.md)
  for the product surface.
- Use `project-management/srs-mini-phases/` as the execution checklist for
  upcoming M-series slices and quality gates.
