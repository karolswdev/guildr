# Architecture

This document describes the current orchestration engine: a LAN-only PWA that
lets an operator follow a project run, review the evidence trail, and intervene
through durable intent events while opencode-backed role agents do the work.

## System Layers

```text
PWA game surface
  Hash-routed vanilla TypeScript application
  GameShell, EventEngine, SceneManager, Object/Story/Goal lenses
  Follow/replay/intervene controls over one folded event ledger

FastAPI backend
  LAN-only HTTP/SSE routes for projects, stream, gates, intents, artifacts,
  memory, metrics, and project brief synthesis

Orchestrator engine
  Workflow state machine, gates, retries, event emission, next-step packets,
  narrator sidecar hooks, narrative digest emission, intent lifecycle handling

Role runtime
  SessionRunner protocol per role
  OpencodeSession for live work
  DryRun*Runner implementations for deterministic local rehearsals

Model providers
  Declared in config.yaml as endpoints + routing
  Local llama.cpp, OpenRouter, OpenAI-compatible, and other opencode-supported
  providers can be mixed per role
```

## Key Modules

| Module | Purpose |
| --- | --- |
| `orchestrator/engine.py` | Workflow state machine, phase/gate execution, event emission, next-step and narrator hooks |
| `orchestrator/lib/config.py` | Core orchestrator settings from YAML or environment |
| `orchestrator/lib/endpoints.py` | Declarative endpoint/routing parser used by live runs |
| `orchestrator/lib/opencode.py` | `SessionRunner` protocol plus `OpencodeSession` subprocess adapter |
| `orchestrator/lib/opencode_config.py` | Per-project `.orchestrator/opencode/opencode.json` generation |
| `orchestrator/lib/opencode_audit.py` | Converts opencode exports into raw I/O and usage rows |
| `orchestrator/lib/events.py` | Durable event bus and SSE replay source |
| `orchestrator/lib/gates.py` | Canonical human gate registry shared by engine and backend |
| `orchestrator/lib/intents.py` | Durable operator intent registry and apply/ignore lifecycle |
| `orchestrator/lib/next_step.py` | Deterministic next-step packets with source refs and memory provenance |
| `orchestrator/lib/narrative.py` | Deterministic narrative digests written as JSON and Markdown artifacts |
| `orchestrator/lib/narrator_sidecar.py` | Debounced narrator coordination around phase, gate, and intent triggers |
| `orchestrator/lib/discussion.py` | Durable discussion log and highlights from operators/personas |
| `orchestrator/lib/memory_palace.py` | Optional MemPalace sync/search/status packet and provenance refs |
| `orchestrator/lib/workflow.py` | Configurable workflow step list, including memory/persona/narrator steps |
| `web/backend/routes/*.py` | Project, stream, gate, intent, artifact, metrics, memory, and brief APIs |
| `web/frontend/src/game/*` | PWA game shell, Three.js scene, map controls, and lenses |
| `web/frontend/src/event-engine/*` | Event replay/folding into current and historical UI snapshots |

## Role Runtime

Roles no longer share one direct chat-completion client. Each opencode-driven
role receives a `SessionRunner` with one method:

```python
runner.run(prompt)  # returns an OpencodeResult
```

Live CLI and backend runs build one `OpencodeSession` per routed role from the
same `endpoints:` and `routing:` block. Dry runs set `dry_run=True`; the engine
then auto-provides deterministic runners for architect, judge, coder, tester,
reviewer, narrator, and deployer.

| Role | Current responsibility |
| --- | --- |
| `memory_refresh` | Sync/search optional MemPalace state before planning |
| `persona_forum` | Capture founding-team perspectives and discussion entries |
| `architect` | Turn `qwendea.md` into a sprint plan |
| `judge` | Validate and score architect output |
| `coder` | Use opencode tools to edit project files task by task |
| `tester` | Run evidence commands and write `TEST_REPORT.md` |
| `reviewer` | Compare implementation against sprint plan and test evidence |
| `narrator` | Produce sourced, neutral project synthesis for the PWA dialogue layer |
| `deployer` | Produce deployment notes and required environment guidance |

## Event And Replay Model

The durable event ledger is the spine of the product. The backend streams live
events over SSE and the frontend folds the same events into replayable
snapshots. This gives the PWA one truth source for:

- workflow progress and phase transitions;
- human gate creation and decisions;
- raw operator intents plus applied/ignored terminal outcomes;
- next-step packets and narrator-refined packets;
- narrative digests and discussion highlights;
- memory provenance refs, artifact refs, and source refs;
- Object, Story, and Goal lens state in the map surface.

The replay is intentionally semantic rather than filesystem time travel. A
snapshot answers what the system knew, what it planned to do next, and where an
operator could have intervened at that point in the run.

## PWA Surface

The PWA is a working cockpit, not a dashboard bolted beside the engine.
`GameShell` renders the map, HUD, intervention compose dock, narrator dialogue,
and lens sheets over one `EventEngine` snapshot. `SceneManager` renders the
spatial objects and focus transitions. The current map surface includes:

- **Next-Step Sheet** for the next slated action, queued intents, memory refs,
  source refs, and nudge/intercept affordances.
- **Object Lens** for the selected workflow object, its recent story,
  artifact refs, source refs, and intent history.
- **Story Lens** for replay-folded digests, discussion rows, risks, and
  highlighted atoms.
- **Goal Core** for project purpose, founding-team context, forum excerpts,
  current progress, and source refs.
- **Narrator dialogue** rendered as a visually rich project-synthesis overlay.
  The narrator persona is neutral; only the presentation borrows from classic
  dialogue-box affordances.

## Dry-Run Mode

Use dry-run mode when you need a deterministic local rehearsal without a model
server or opencode provider. The engine wires the role-specific dry-run runners
itself.

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
print("dry-run smoke passed")
```

Expected artifacts include `sprint-plan.md`, `README.md`, `TEST_REPORT.md`,
`REVIEW.md`, `DEPLOY.md`, `.orchestrator/logs/raw-io.jsonl`, narrative digest
files, discussion rows, and replayable event records.

## Live Run Configuration

Live runs require a YAML config with `endpoints:` and `routing:`. The CLI turns
that declaration into a per-project opencode config and passes role-specific
sessions into the engine.

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

Run it with:

```bash
guildr run --config config.yaml --no-gates
```

Use `--gate` for attended runs that pause at human gates. The PWA and CLI share
the same gate registry path when launched through the backend runner.

## Operator Memory

MemPalace is optional but first-class when present. `memory_refresh` can write a
project wake-up packet, and `memory_provenance()` attaches compact refs to
next-step packets and narrator inputs. The UI should treat memory as cited
context, not hidden global state: every memory-backed statement needs a source
or artifact ref that can be shown in the lens sheets.

## Audit And Quality Gates

Every opencode session is translated into:

- `raw-io.jsonl` rows for forensic prompt/response inspection;
- `usage.jsonl` rows keyed to the same call id;
- event-ledger updates for follow/replay surfaces;
- artifact refs for sprint plans, reports, reviews, deployments, digests, and
  discussion outputs.

Human gates sit between major phases. Operator intents are separate from gate
decisions: they are queued, attached to the next relevant packet, applied into
role prompts when supported, or marked ignored with a terminal reason when the
target step has passed.
