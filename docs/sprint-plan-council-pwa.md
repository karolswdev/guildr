# Sprint Plan: Council PWA And Replay Spine

## Purpose

This sprint turns the Council Engine design into an executable, replayable, and
visually tangible PWA system.

The plan is written for low-context execution. Each task lists the exact
context files to read, the implementation surface, acceptance criteria, and
evidence commands. Agents should consume one task packet at a time and avoid
loading the full repository unless the task explicitly requires it.

## Sprint Goal

Deliver the first end-to-end spine where:

- backend events are schema-valid and replay-safe,
- model/provider usage is recorded,
- llama.cpp local telemetry is normalized,
- SDLC loop state is emitted,
- EventEngine folds atoms, cost, loops, and memory from event history,
- the PWA can replay the run from durable events,
- the Three.js route starts using the vendored asset system.

The first release does not need every visual flourish. It must prove the spine.

## Source Specs

Use these as the required context set:

- `docs/srs-council-engine.md`
- `docs/cost-tracking.md`
- `docs/sdlc-loop-visualization.md`
- `docs/threejs-client-architecture.md`
- `docs/threejs-integration-plan.md`
- `docs/threejs-asset-pipeline.md`
- `docs/ux-interaction-model.md`
- `docs/visual-grammar.md`
- `docs/implementation-roadmap.md`
- `assets/README.md`

## Non-Negotiable Invariants

- Every persisted run event has `event_id`, `schema_version`, `run_id`, `ts`,
  and `type`.
- Replay derives state by folding events. It never depends on mutable UI state.
- Usage and cost are recorded as `usage_recorded` events.
- Historical replay never recomputes old provider pricing from today's prices.
- llama.cpp telemetry is local telemetry first, dollar estimate second.
- SDLC loop state is emitted as events and folded into `LoopSnapshot`.
- The PWA uses vendored assets through `AssetManager`; no runtime hotlinks.
- The Three.js scene remains usable without optional assets.
- iPhone portrait is the baseline UX target.

## Definition Of Done

The sprint is done when:

- `uv run pytest -q` passes.
- Frontend build passes.
- Event ledger schema tests cover happy path and rejection path.
- EventEngine fixture tests prove replay for atoms, cost, and loops.
- A fixture llama.cpp response produces normalized usage and telemetry.
- PWA history load and SSE append deduplicate by `event_id`.
- The asset manifest loads core vendored assets and excludes reference-only
  assets from first render.
- A replay fixture can show an atom moving build -> verify -> repair -> verify.

## Task 1: Event Schema And Ledger Hardening

### Goal

Make the event ledger authoritative, versioned, and safe to replay.

### Context

- `docs/srs-council-engine.md`
- `docs/threejs-integration-plan.md`
- Current backend event stream and events routes.

### Implementation Surface

- Backend event model/types.
- Event bus emit path.
- `.orchestrator/events.jsonl` writer.
- Event history route.

### Requirements

- Add a shared event validation model.
- Generate ULID-style `event_id` for events that do not already have one.
- Require `schema_version`.
- Require `run_id` for run events.
- Reject unknown future schema versions at read/fold boundaries.
- Deduplicate history/SSE by `event_id`, not timestamp.

### Acceptance Criteria

- Invalid event without `event_id` or `schema_version` is rejected before
  ledger write, unless the write path is explicitly responsible for adding it.
- History endpoint returns event ids.
- SSE subscribers receive event ids.
- Duplicate SSE replay does not duplicate state.

### Evidence

```bash
uv run pytest -q web/backend/tests tests
```

## Task 2: Provider Usage Event Emission

### Goal

Every LLM or advisor call emits one normalized `usage_recorded` event.

### Context

- `docs/cost-tracking.md`
- Provider/client code for local llama, OpenAI-compatible, OpenRouter, CLI
  advisors, and fake provider.

### Implementation Surface

- Provider abstraction.
- LLM call wrapper.
- CLI advisor wrapper.
- Event bus.

### Requirements

- Normalize provider kind, provider name, model, role, step, atom id, attempt,
  call id, usage tokens, runtime, cost, source, confidence, and extraction path.
- Emit usage for failed calls when partial usage exists.
- Preserve provider-reported usage/cost metadata.
- Keep secrets out of events and logs.

### Acceptance Criteria

- Fake provider emits deterministic usage events in tests.
- Provider failures emit structured error events and usage when available.
- No API keys or Authorization headers appear in event payloads.

### Evidence

```bash
uv run pytest -q tests web/backend/tests
rg -n "Authorization|api_key|OPENROUTER_API_KEY" .orchestrator 2>/dev/null || true
```

## Task 3: llama.cpp Telemetry Normalization

### Goal

Make local llama.cpp runs visible in the same replay/cost system while showing
local inference health separately from spend.

### Context

- `docs/cost-tracking.md`
- `docs/threejs-integration-plan.md`
- Existing llama/local provider client code.

### Implementation Surface

- llama.cpp provider adapter.
- Usage normalization helpers.
- Tests with fixture responses.

### Requirements

- Extract OpenAI-compatible `usage` fields when present.
- Extract llama.cpp `timings` fields when present.
- Preserve `runtime.llamacpp`.
- Treat `/metrics` and `/slots` as supplemental only.
- Use `local_estimate` and correct confidence semantics.

### Acceptance Criteria

- Fixture with `timings.prompt_n`, `cache_n`, and `predicted_n` maps to input,
  cache, output, context tokens, and throughput.
- Missing metrics endpoint does not fail a call.
- Local estimate uses the versioned local cost profile.

### Evidence

```bash
uv run pytest -q tests web/backend/tests
```

## Task 4: Budget Gates And Cost Folding

### Goal

Budget state is durable, replayable, and visible at every scrub position.

### Context

- `docs/cost-tracking.md`
- `docs/threejs-integration-plan.md`
- Gate control routes.

### Implementation Surface

- Budget event emitter.
- Gate decision route.
- EventEngine cost reducer.
- Economics fixture tests.

### Requirements

- Emit `budget_warning`, `budget_exceeded`, `budget_gate_opened`, and
  `budget_gate_decided`.
- Fold `remainingRunBudgetUsd`, `remainingPhaseBudgetUsd`, and `runHalted`.
- Use recorded budget-at-decision values, not recomputed current totals.

### Acceptance Criteria

- Replay at index before a gate shows old budget.
- Replay at index after a gate shows post-decision budget.
- Rejected budget gate halts run state but replay continues to display later
  events if present.

### Evidence

```bash
uv run pytest -q web/frontend web/backend/tests tests
```

## Task 5: SDLC Loop Event Emission

### Goal

Atoms expose lifecycle state that can be replayed and rendered physically.

### Context

- `docs/sdlc-loop-visualization.md`
- `docs/srs-council-engine.md`
- Workflow/phase execution code.

### Implementation Surface

- Workflow phase runner.
- Event bus.
- Phase handlers.

### Requirements

- Emit loop events for discover, plan, build, verify, repair, review, ship,
  and learn where applicable.
- Emit repair loop on verifier failure and guru escalation.
- Emit learn loop on MemPalace sync/wake-up refresh.
- Include artifact, evidence, memory refs when available.

### Acceptance Criteria

- A failing verification fixture produces verify -> repair -> verify events.
- A memory refresh fixture produces learn loop events.
- Loop events are valid ledger events.

### Evidence

```bash
uv run pytest -q tests web/backend/tests
```

## Task 6: EventEngine Extraction

### Goal

Create the single frontend reducer that drives current DOM views and future
Three.js views.

### Context

- `docs/threejs-integration-plan.md`
- Current `web/frontend/src/views/Progress.ts`.

### Implementation Surface

- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- Existing Progress view integration.

### Requirements

- Load history before opening SSE.
- Deduplicate by `event_id`.
- Fold atom state, cost state, loop state, and memory status.
- Support `scrubTo(index)` and `resumeLive()`.
- Keep current Progress view working.

### Acceptance Criteria

- Fixture tests for atom replay.
- Fixture tests for cost replay.
- Fixture tests for loop replay.
- Progress view consumes EventEngine snapshots.

### Evidence

```bash
./web/frontend/build.sh
uv run pytest -q
```

## Task 7: AssetManager And Runtime Asset Manifest

### Goal

Make the Three.js scene consume the vendored asset kit safely and consistently.

### Context

- `assets/README.md`
- `docs/threejs-asset-pipeline.md`
- `docs/visual-grammar.md`

### Implementation Surface

- `web/frontend/src/game/assets/manifest.ts`
- `web/frontend/src/game/assets/AssetManager.ts`
- GameShell bootstrap.

### Requirements

- Centralize all asset paths.
- Load core assets before first scene render.
- Delay HDRI until after first render unless profiled safe.
- Exclude `post-processing-refs/lensDirt1.png` from initial runtime.
- Expose loading progress to the PWA shell.

### Acceptance Criteria

- Browser network panel shows local asset paths only.
- Missing optional asset uses placeholder and does not break interaction.
- First scene does not request lens dirt.
- Asset folder sources/licenses remain documented.

### Evidence

```bash
./web/frontend/build.sh
```

Manual evidence:

- Screenshot of browser network panel filtered to `assets/`.
- Screenshot of first scene render.

## Task 8: First Three.js Map Route

### Goal

Render the first tangible orchestration map with atoms, edges, hex grid, and
basic interaction.

### Context

- `docs/threejs-client-architecture.md`
- `docs/visual-grammar.md`
- `docs/ux-interaction-model.md`
- `docs/threejs-asset-pipeline.md`

### Implementation Surface

- GameShell.
- SceneManager.
- AtomNode.
- EdgeMesh.
- Basic route/view integration.

### Requirements

- Render atom nodes over the vendored hex-grid substrate.
- Use atom material assets when available.
- Pan, pinch, tap, and fit-all work.
- FocusPanel opens from selected atom.
- Fallback DOM view works without WebGL.

### Acceptance Criteria

- iPhone portrait layout is usable.
- Desktop layout is usable.
- WebGL failure path remains controllable.
- No decorative card frame around the primary scene.

### Evidence

```bash
./web/frontend/build.sh
```

Manual evidence:

- Desktop screenshot.
- Mobile screenshot.
- WebGL-disabled fallback screenshot.

## Task 9: Replay HUD, Cost HUD, And Loop Lane

### Goal

Make replay feel operational: timeline scrubbing changes atom state, cost, and
SDLC loop state.

### Context

- `docs/ux-interaction-model.md`
- `docs/visual-grammar.md`
- `docs/cost-tracking.md`
- `docs/sdlc-loop-visualization.md`

### Implementation Surface

- ReplayTimeline.
- CostHud.
- EconomicsSheet.
- Loop lane and loop lens.
- FocusPanel.

### Requirements

- Timeline can scrub by event index.
- Cost HUD reflects selected replay point.
- Economics sheet opens summary-first, not table-first.
- Loop lane filters by SDLC stage.
- FocusPanel shows local llama telemetry when available.

### Acceptance Criteria

- Scrub to start shows zero cost and idle loops.
- Scrub after a usage event updates cost.
- Scrub after verify failure shows repair loop.
- llama.cpp fixture atom shows context/cache/throughput telemetry.

### Evidence

```bash
./web/frontend/build.sh
uv run pytest -q
```

Manual evidence:

- Short screen recording of replay scrub.

## Task 10: MemPalace And Learn Loop Visualization

### Goal

Make memory visible as part of the world model, not a side tab.

### Context

- `docs/sdlc-loop-visualization.md`
- `docs/threejs-client-architecture.md`
- `docs/visual-grammar.md`
- Existing memory routes.

### Implementation Surface

- MemPalaceGroup.
- MemoryOrb.
- LoopLayer.
- FocusPanel memory detail.

### Requirements

- Memory arc is persistent and non-occluding.
- Learn loop events connect atoms to MemPalace.
- Memory search results orbit relevant atoms.
- Wake-up packet state is visible in focus/detail UI.

### Acceptance Criteria

- Memory refresh produces visible learn loop transition.
- Memory search result can be opened from the map.
- The map remains readable with memory arc enabled.

### Evidence

```bash
./web/frontend/build.sh
uv run pytest -q
```

## Task 11: Design Review Gate

### Goal

Apply the review protocol before promoting the Three.js map to the default
Progress experience.

### Context

- `docs/design-review-protocol.md`
- All implementation evidence from Tasks 1-10.

### Implementation Surface

- Review notes.
- Issue/PR comment or docs note.
- PWA design review status.

### Requirements

- Review hats: systems, FinOps/provider, mobile game UX, local inference,
  security/operator safety.
- External reviewers are read-only unless scoped to disjoint files.
- Findings become concrete tasks or explicit accepted risks.

### Acceptance Criteria

- Review notes are committed or attached to the PR.
- No unresolved critical finding remains.
- Accepted risks are documented.

### Evidence

```bash
git status -sb
```

## Execution Order

Recommended sequence:

1. Task 1: Event schema and ledger hardening.
2. Task 2: Provider usage event emission.
3. Task 3: llama.cpp telemetry normalization.
4. Task 4: Budget gates and cost folding.
5. Task 5: SDLC loop event emission.
6. Task 6: EventEngine extraction.
7. Task 7: AssetManager and manifest.
8. Task 8: First Three.js map route.
9. Task 9: Replay HUD, Cost HUD, and Loop Lane.
10. Task 10: MemPalace and Learn Loop visualization.
11. Task 11: Design review gate.

Tasks 2, 3, and 5 can be split among agents after Task 1 lands. Tasks 7 and 8
can begin after Task 6 defines the snapshot contract, but the scene can use
fixtures while backend events are still being finalized.

## Context Packet Template

Each low-context agent should receive:

```text
Goal:
<one task goal>

Context files:
<only the files listed for that task>

Allowed write scope:
<specific files or directories>

Acceptance criteria:
<copy from task>

Evidence:
<commands and manual screenshots if applicable>

Non-goals:
- Do not refactor unrelated modules.
- Do not change event semantics outside this task.
- Do not load extra design docs unless blocked.
```

## First Task Packet

Start with Task 1. It unlocks everything else.

Allowed write scope:

- backend event model/helpers,
- event bus,
- event history route,
- backend tests for event validation and dedup.

Do not start visual work until event identity and schema versioning are real.
