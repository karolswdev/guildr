# Software Requirements Specification: Council Engine

## 1. Purpose

This document defines the target system for the Council Engine: a low-context,
memory-first orchestration platform for building software through multiple
specialized agents, human intervention, durable event streams, and a PWA that
makes the whole process observable, replayable, and controllable.

The system baseline is models with context windows up to 128k tokens. The
architecture must also remain useful below that limit. The central design goal
is to avoid depending on one large prompt that remembers everything. Instead,
the platform must use durable memory, atomic work packets, explicit goals,
traceable artifacts, and event replay.

MemPalace is not optional. It is the memory spine of the system.

## 2. Product Vision

The Council Engine should feel like a command surface for a living build
operation. The user should be able to watch agents coordinate in real time,
pause or redirect execution, inspect memory, replay successful runs, and reuse
the system against different projects without rewriting prompts by hand.

The PWA is not a thin debug console. It is the primary operating surface.
It must eventually feel closer to a tactical game interface than a form stack:
clear state, readable movement, fast controls, rich replay, visible history,
and direct manipulation of workflow atoms.

## 3. Definitions

- Atom: The smallest executable unit of orchestration. Examples: memory
  refresh, persona forum turn, architect decomposition, micro-task packet,
  implementation slice, verifier pass, escalation consultation, gate decision.
- Memory spine: The mandatory MemPalace-backed project and agent memory layer.
- Wake-up packet: A bounded memory context produced by MemPalace and carried
  into compact context.
- Phase file: A low-context file that contains all information needed for one
  atomic task or verification step.
- Event ledger: Durable JSONL stream of all run events, used for live PWA
  updates and replay.
- Cost ledger: Replayable usage and economics state emitted into the event
  ledger for every model, advisor, retry, and escalation call.
- Guru advisor: A stronger or external model/tool invoked for a bounded
  unblock plan, such as Codex CLI, Claude CLI, or an OpenAI-compatible model
  through OpenRouter.
- Hook: A configured interception point that can observe, modify, approve,
  block, or add work.

## 4. Operating Principles

1. Memory is mandatory.
   Every serious run begins with memory refresh and produces a wake-up packet.

2. Context is budgeted.
   Prompts must be composed from bounded packets, not unbounded repo state.

3. Work is atomic.
   The architect must decompose work into small, verifiable phase files.

4. Goals are explicit.
   Each atom must know the project goal, local objective, acceptance criteria,
   source requirements, memory inputs, and evidence contract.

5. Events are durable.
   Anything meaningful that happens in the run must be written to the event
   ledger, not only streamed live.

6. The user can intervene.
   The user can inject instructions, edit workflow state, resume from a step,
   compact context, trigger memory refresh, and replay prior runs.

7. Agents are replaceable.
   A role can be served by local models, OpenAI-compatible providers, CLI tools,
   or future adapters if the input and output contract is satisfied.

8. The UI shows causality.
   The PWA must show why an atom exists, what it consumed, what it produced,
   and how it affected later atoms.

9. Cost is visible state.
   Token usage, provider spend, local estimates, and budget gates must be
   recorded as events so live operation and replay agree.

10. Batteries are provided, boundaries are programmable.
   The system must work out of the box with local defaults, while every
   serious boundary remains configurable through durable provider, hook, and
   workflow contracts.

## 5. System Scope

### In Scope

- Project creation and recovery.
- Mandatory MemPalace initialization, mining, wake-up, status, and search.
- Agent workflow definition, editing, and migration.
- Atomic phase file generation.
- Persona/founding-team synthesis.
- Detailed architect decomposition with memory tiers and traceability.
- Resumable workflow execution.
- Human gates and operator checkpoints.
- Guru escalation through CLI and OpenAI-compatible providers.
- Durable event ledger and live SSE streaming.
- Replayable cost and token tracking.
- Replay viewer foundation.
- PWA control room for workflow, memory, logs, events, and intervention.
- Compact context generation for models under or around 128k tokens.

### Out of Scope For Initial Release

- Multi-user authorization.
- Public internet exposure.
- Distributed worker scheduling across machines.
- Full visual replay editor with branching timelines.
- Full visual node graph workflow authoring.
- Marketplace for third-party hooks.

These are future extensions, not design blockers.

## 6. Core Architecture

### 6.1 Memory Spine

The system must use MemPalace as a required project capability.

Requirements:

- The default workflow must include `memory_refresh` before planning phases.
- `memory_refresh` must initialize MemPalace for the project if needed.
- `memory_refresh` must mine project files into the project wing.
- `memory_refresh` must write a wake-up packet to:
  `.orchestrator/memory/wake-up.md`
- Compact context must include the latest palace wake-up packet.
- Operator prompt augmentation must include the latest palace wake-up packet.
- The PWA must expose memory status, sync, wake-up refresh, and search.
- Memory errors must be visible in the event ledger and PWA.

Desired future capability:

- Agent-specific wings or diaries.
- Conversation mining for prior Codex, Claude, and web sessions.
- Memory diffing before/after each phase.
- Memory provenance links from prompt packets back to palace drawers.

### 6.2 Atomic Workflow Model

The workflow must be stored as durable JSON and editable through the PWA.

Each step must contain:

- `id`
- `title`
- `type`: `phase`, `gate`, or `checkpoint`
- `handler`
- `enabled`
- `description`
- `config`

Each atom should additionally expose or derive:

- Inputs consumed.
- Memory used.
- Output artifact.
- Event span.
- Acceptance criteria.
- Evidence required.
- Retry policy.
- Hook points.

The platform must support inserting operator checkpoints and future custom
advisory/review steps without code changes for every user workflow variation.

### 6.3 Architect Requirements

The architect is responsible for converting project intent and memory into a
deterministic sprint plan.

The architect prompt must require:

- Project objective.
- Constraints and non-goals.
- Memory tiers.
- Traceability matrix.
- Atomic tasks.
- Source requirements per task.
- Task memory per task.
- Determinism notes per task.
- Acceptance criteria per task.
- Evidence commands per task.
- Blast-radius notes.

The architect output must be parseable enough for the micro-task breaker to
produce phase files. It should not depend on a later model guessing structure
from loose prose.

### 6.4 Phase Files

Micro-task breakdown must produce low-context packets.

Each implementation packet must include:

- Task title.
- Goal.
- Background.
- Relevant memory.
- Files allowed or expected to change.
- Exact acceptance criteria.
- Evidence required.
- Out-of-scope items.
- Known dependencies.

Each verification packet must include:

- What to verify.
- Test commands.
- Failure interpretation.
- Required evidence.
- Retry escalation criteria.

These packets are the main way small-context models succeed.

### 6.5 Guru Escalation

Guru escalation is a bounded advisory stage, not an uncontrolled code mutator.

Supported advisor types:

- Local CLI: `codex`
- Local CLI: `claude`
- OpenAI-compatible HTTP providers.
- OpenRouter configured as an OpenAI-compatible provider.

Requirements:

- Each advisor call must receive a compact packet, not the whole repo.
- Each advisor must return a remediation plan.
- The plan must be decomposed into atomic, verifiable steps.
- Advisor output must be written as an artifact.
- Advisor calls must be visible in the event ledger.
- Credentials must be configured through environment variables or secure local
  config, never committed.

OpenRouter requirements:

- Support base URL override.
- Support model selection per workflow step.
- Support request timeout.
- Support max tokens.
- Support temperature and reasoning/profile hints where provider-compatible.
- Persist advisor request metadata without logging secrets.

## 7. Hookability Requirements

The system must be aggressively hookable.

Hook points:

- Before workflow step starts.
- After workflow step completes.
- On phase failure.
- Before retry.
- Before context compaction.
- After memory refresh.
- Before advisor escalation.
- After advisor escalation.
- Before gate opens.
- After gate decision.
- Before file write.
- After test run.
- Before deployment.

Hook capabilities:

- Observe event and state.
- Add operator instruction.
- Mutate workflow config within allowed bounds.
- Add checkpoint.
- Trigger memory search.
- Trigger memory sync.
- Request guru escalation.
- Block continuation with a gate.
- Write artifact.
- Emit custom event.

Hook configuration must be durable and project-scoped.

Hook outputs must be recorded in:

- Event ledger.
- Agent logs when attached to a phase.
- Artifacts when content is long-lived.

Hooks must be sandbox-aware. A hook cannot silently access secrets or write
outside the project unless explicitly permitted by configuration.

## 8. Event Ledger And Replay

The event ledger is the canonical run stream.

Requirements:

- All live SSE events must also be persisted to `.orchestrator/events.jsonl`.
- Each event must contain:
  - `ts`
  - `type`
  - step or phase identifier when applicable
  - project id when applicable
  - attempt when applicable
  - decision when applicable
  - error when applicable
  - metadata payload when applicable
- The backend must expose event history through an API.
- The PWA must load durable event history before or alongside SSE.
- The PWA must support filtering by event type and step.
- The PWA must support replay from durable history.
- Model and advisor usage must be recorded through `usage_recorded` events.

Replay viewer requirements:

- Play, pause, fast-forward, rewind.
- Scrub timeline by event index or time.
- Filter by phase, role, event type, error, gate, memory, or advisor.
- Show event detail payload.
- Show artifact diffs if event references artifacts.
- Show memory state before/after when available.
- Show cost and token counters as of the selected replay point.
- Export replay as a diagnostic bundle.

Future replay requirements:

- Branch from a prior event into a new run.
- Mark a successful run as a template.
- Compare two runs side-by-side.

### 8.1 Cost Ledger And Budget Replay

Cost tracking is a first-class projection over the event ledger.

Requirements:

- Every LLM, local model, advisor, retry, and escalation call must emit one
  `usage_recorded` event.
- `usage_recorded` events must include provider kind, provider name, model,
  call id, role, step, atom id, token usage, runtime, cost, source, confidence,
  and budget state when known.
- Cost source must be explicit: `provider_reported`, `rate_card_estimate`,
  `local_estimate`, or `unknown`.
- Provider-returned usage and cost metadata must be preserved when available.
- Local model calls must be tracked with wall time, throughput, and configured
  machine-cost estimates.
- Historical replay must use recorded events and recorded rate-card snapshots,
  not today's pricing.
- Budget warnings, budget gates, and budget decisions must be durable events.

Budget levels:

- Project budget.
- Run budget.
- Phase budget.
- Provider budget.
- Escalation budget.
- Per-call hard cap.

Replay cost snapshots must expose:

- Total effective run cost.
- Provider-reported total.
- Estimated total.
- Unknown-cost count.
- Cost by provider, model, role, phase, and atom.
- Token totals by input, output, cache, and reasoning.
- Budget remaining at the selected replay point.

The detailed design is governed by `docs/cost-tracking.md`.

## 9. PWA Requirements

The PWA must feel like a high-trust operating surface.

Core screens:

- Project list.
- Project setup.
- Quiz/PRD gathering.
- Mission Control.
- Gates.
- Artifacts.
- Replay viewer.
- Economics and budget panel.
- Memory palace browser.
- Workflow editor.

Mission Control must include:

- Current focus.
- Next step.
- Live telemetry.
- Live cost and token telemetry.
- Latest signal.
- Workflow board.
- Step inspector.
- Founding team editor.
- Palace memory panel.
- Event timeline.
- Event detail.
- Terminal peek.
- Durable log tabs.

Interaction requirements:

- Drag to reorder workflow steps.
- Toggle steps.
- Add checkpoints.
- Inject operator instructions.
- Scope instructions to phases.
- Compact context.
- Resume from any enabled step.
- Trigger memory sync.
- Trigger wake-up refresh.
- Search memory.
- Inspect durable logs with indentation preserved.
- Load prior event history.
- Inspect spend by provider, model, role, phase, and atom.
- Pause or resume through budget gates.

Game-like UX direction:

- The workflow should eventually render as an interactive map of atoms.
- Each atom should expose connections to memory, artifacts, gates, and other
  atoms.
- Status should be spatial and animated enough to feel alive, but never at the
  cost of clarity.
- Replay should feel like scrubbing a tactical timeline.

## 10. Agent Coordination Requirements

Agents must work on the same page through shared artifacts and evented state.

Coordination mechanisms:

- Shared project goal in compact context.
- MemPalace wake-up packet.
- Workflow step config.
- Phase files.
- Event ledger.
- Artifact references.
- Gate decisions.
- Operator instructions.

Each atom must know:

- Why it exists.
- What goal it advances.
- What it is allowed to change.
- What memory it should trust.
- What artifact it must emit.
- What evidence proves completion.
- What should trigger escalation.

No agent should rely on invisible chat state.

## 11. Model Provider Requirements

The system must support multiple model execution styles.

Provider classes:

- Local llama server.
- OpenAI-compatible HTTP API.
- OpenRouter as OpenAI-compatible.
- CLI advisors.
- Dry-run fake model for tests.
- Future local or hosted adapters.

Provider config must include:

- Provider kind.
- Base URL.
- Model name.
- API key environment variable.
- Timeout.
- Max tokens.
- Temperature.
- Context budget.
- Retry limits.
- Budget limits.
- Cost profile or rate-card source.

The context budget must be explicit per phase. The default design target is
128k tokens or below, with smaller packets preferred.

Provider behavior must follow a batteries-provided model:

- A local model path should work with minimal configuration.
- MemPalace should work as the default memory substrate.
- Dry-run should work in tests without external services.
- OpenRouter should be configurable without writing code.
- CLI tools should be invokable through provider config.
- Provider contracts should be shared across phases, hooks, and advisor calls.
- Provider failures should produce structured events and remediation options.

Provider configuration must be programmable:

- Workflow steps can choose provider profiles.
- Hooks can override provider choice within permission limits.
- Escalation steps can call multiple providers and compare outputs.
- Replay can show which provider produced which artifact.
- The PWA can expose provider health, model, cost/risk hints, and context
  budget per atom.
- Replay can show token and cost totals exactly as they were recorded at the
  selected event index.

The goal is not to lock the user into our infrastructure. The goal is to
provide strong defaults while allowing the user to mix local models, hosted
OpenAI-compatible endpoints, OpenRouter, CLI tools, and future adapters within
one coherent orchestration contract.

## 12. Data And Artifacts

Project-local durable files:

- `.orchestrator/project.json`
- `.orchestrator/state.json`
- `.orchestrator/control/workflow.json`
- `.orchestrator/control/context.compact.md`
- `.orchestrator/control/instructions.jsonl`
- `.orchestrator/events.jsonl`
- `.orchestrator/logs/*.jsonl`
- `.orchestrator/costs/run-summary.json`
- `.orchestrator/costs/provider-ledger.jsonl`
- `.orchestrator/costs/rate-cards/*.json`
- `.orchestrator/memory/wake-up.md`
- `.orchestrator/memory/status.txt`
- `.orchestrator/memory/last-search.txt`
- `mempalace.yaml`
- `entities.json`
- `FOUNDING_TEAM.json`
- `PERSONA_FORUM.md`
- `sprint-plan.md`
- `phase-files/*`
- `TEST_REPORT.md`
- `REVIEW.md`
- `DEPLOY.md`

Artifacts must be linkable from events whenever possible.

## 13. Nonfunctional Requirements

Performance:

- PWA interactions should respond within 100 ms for local state changes.
- Event stream updates should appear within 1 second.
- Event history queries should support at least 5,000 events per project.
- Memory sync may be slower, but must show progress or blocking state.

Reliability:

- Runs must survive PWA refresh.
- Event history must survive server restart.
- Workflow config must survive server restart.
- Memory packets must be reusable across sessions.

Security:

- LAN-only default.
- No secret logging.
- Advisor API keys only through environment or secure local config.
- Project path traversal protection.
- No uncontrolled public exposure.

Portability:

- Mac first.
- Python environment must be explicit through `uv`.
- PWA must run from the local backend.
- No required cloud service for core local operation.

Observability:

- Every phase writes logs.
- Every run writes events.
- Every memory operation writes status artifacts.
- Every escalation writes advisor output.
- Every model and advisor call writes usage and cost events.

## 14. Milestones

### Milestone 1: Memory Spine And Replay Foundation

- Mandatory `memory_refresh` phase.
- MemPalace dependency.
- Memory status/sync/wake-up/search routes.
- Compact context includes palace wake-up.
- Event ledger persists SSE events.
- Event history API.
- PWA loads event history.

### Milestone 2: Atomic Coordination

- Atom metadata schema.
- Phase file index improvements.
- Task dependency graph.
- Step-to-artifact references.
- Step-to-memory references.
- Hook points persisted in workflow config.

### Milestone 3: Replay Viewer

- Timeline scrubber.
- Event filters.
- Fast-forward controls.
- Event detail pane.
- Artifact links.
- Replayable cost snapshots.
- Replay export bundle.

### Milestone 4: Provider And Guru Mesh

- OpenAI-compatible provider abstraction.
- OpenRouter config UI.
- Cost adapters for hosted, OpenAI-compatible, CLI, and local providers.
- Budget gates.
- Provider health checks.
- Advisor output contracts.
- Escalation-to-microtask decomposition.

### Milestone 5: Game-Like PWA Surface

- Workflow atom map.
- Animated run state.
- Memory palace browser.
- Agent council panel.
- Replay theater.
- Direct manipulation for inserting and connecting atoms.

## 15. Acceptance Criteria

The Council Engine is on target when:

- A new project can run from memory refresh through deployment.
- The architect produces traceable atomic tasks.
- A small-context model can execute a phase file without full repo context.
- The PWA can show live events and load prior events after refresh.
- MemPalace wake-up is included in compact context.
- The user can inject instructions and resume from workflow steps.
- A failed phase can request advisor escalation.
- Advisor output can be broken into atomic remediation tasks.
- A successful run can be replayed from durable events.
- Replay shows the cost, tokens, source, confidence, and budget state that were
  known at that replay point.
- The system can run locally without cloud dependencies, while still allowing
  configured OpenRouter or other OpenAI-compatible advisors.

## 16. Open Questions

- Should MemPalace use one global palace with project wings, or a per-project
  palace path by default?
- How should event ledger payloads reference large artifacts without bloating
  the ledger?
- What hook permissions should be available to user-defined scripts?
- Should replay branches fork workflow config, project files, or both?
- How should conflicting persona/forum advice be resolved deterministically?
- Which visual grammar should the atom map use for phases, gates, checkpoints,
  memory, and advisors?
- What default local machine cost profile should ship for first-run setup?

## 17. Current Implementation Status

Implemented:

- Mandatory `memory_refresh` workflow phase.
- MemPalace dependency.
- Memory sync, wake-up, status, and search backend routes.
- Palace wake-up included in compact context and operator prompt context.
- Durable event ledger written from live SSE events.
- Event history API.
- Cost tracking design.
- PWA Palace Memory panel.
- PWA event history loading.
- Workflow board, step inspector, founding team editor, terminal peek.

Not yet implemented:

- Full replay viewer controls.
- Visual atom map.
- Hook engine and hook permissions.
- OpenRouter provider UI.
- Runtime cost event emission.
- Budget gates.
- Event-to-artifact cross-links.
- Agent diary mining.
- Replay branching.

## 18. Three.js Client Design Documents

The PWA direction is now governed by the following design documents:

- `docs/threejs-product-direction.md`
- `docs/threejs-client-architecture.md`
- `docs/ux-interaction-model.md`
- `docs/visual-grammar.md`
- `docs/threejs-integration-plan.md`
- `docs/implementation-roadmap.md`
- `docs/cost-tracking.md`

These documents supersede the idea of the Progress view as a conventional
admin console. The long-term default project run view is a Three.js strategy
map driven by the event ledger, with DOM overlays for text, accessibility,
controls, and fallback operation.
