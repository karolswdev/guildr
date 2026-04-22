# M02B — Intent Lifecycle Execution Plan

## Purpose

Make operator intervention honest. The PWA must not merely collect suggestions; it must show each submitted intent moving through a visible lifecycle and prove whether it affected a prompt, artifact, gate, or workflow decision.

This plan is the concrete execution sequence after M02a. It assumes deterministic `next_step_packet_created` exists and includes M08 memory provenance.

## Investigation Baseline

Current codebase state:

- `web/backend/routes/intents.py` accepts `operator_intent` and persists a scrubbed event.
- `orchestrator/lib/next_step.py` builds authoritative next-step packets with memory provenance.
- `orchestrator/engine.py` emits `next_step_packet_created` before phase start and after phase/gate approval.
- `orchestrator/lib/control.py` reads `.orchestrator/control/instructions.jsonl` and appends matching instructions into role prompts.
- `append_operator_context()` has no idea which `operator_intent` created an instruction, so it cannot emit `operator_intent_applied`.
- `EventEngine` folds `nextStepPacket`, memory, cost, loops, and atoms, but does not yet fold pending/applied/ignored intents.
- `GameShell` already has map interaction surfaces (`bottom-chip-cluster`, `radial-action-ring`, `compose-dock`) and posts intents, but it does not show terminal outcomes.

Implication:

The next implementation must bridge **operator_intent event -> durable instruction -> prompt injection -> terminal outcome event -> PWA lifecycle fold**.

## Execution Rules

- PWA is the priority surface. Every backend primitive must support a visible map/sheet state.
- Do not add a dashboard/table as the primary surface.
- Do not create a second event ledger or second instruction store.
- Do not mark an intent applied unless a prompt/context/artifact actually consumed it.
- Every submitted `client_intent_id` must end with exactly one terminal event.
- All new events must satisfy G1: `event_id`, `schema_version`, `ts`, `type`, `run_id`.
- All prompt-facing intent text must pass through `orchestrator/lib/scrub.py`.

## Target Event Contracts

### `operator_intent`

Already exists. Required fields for M02b:

- `client_intent_id`
- `kind`
- `atom_id`
- `payload`
- `project_id`

If PWA omits `client_intent_id`, backend must create one and return it.

### `operator_intent_applied`

Emit when an intent is injected into a prompt/context or transformed into a durable control decision.

Required payload:

- `client_intent_id`
- `intent_event_id`
- `kind`
- `atom_id`
- `applied_to`: `prompt_context`, `workflow_control`, `gate_hold`, or `discussion_note`
- `step`
- `artifact_refs`
- `source_refs`

### `operator_intent_ignored`

Emit when an intent cannot affect the run.

Required payload:

- `client_intent_id`
- `intent_event_id`
- `kind`
- `atom_id`
- `reason`: `target_step_passed`, `scope_mismatch`, `unsupported_kind`, `superseded`, or `invalid_payload`
- `source_refs`

## Sequential Execution Plan

### Step 1 — Backend Intent Registry

Files:

- `web/backend/routes/intents.py`
- new `orchestrator/lib/intents.py`
- tests: `web/backend/tests/test_intents.py`, new or extended `tests/test_intents.py`

Status: Done 2026-04-22.

Implementation:

- Add `orchestrator/lib/intents.py`.
- Store accepted intents in `.orchestrator/control/intents.jsonl`.
- Each row includes `client_intent_id`, emitted `intent_event_id`, `kind`, `atom_id`, scrubbed payload, status `queued`.
- Backend returns `client_intent_id`.
- If request omitted it, generate deterministic-looking local id such as `intent_<event-id>`.

Quality gate after Step 1:

- `POST /intents` persists exactly one queued row.
- Event and JSONL row share the same `client_intent_id`.
- Secret strings are absent from event log and JSONL.
- Test command:

```bash
uv run pytest -q web/backend/tests/test_intents.py tests/test_intents.py
git diff --check
```

### Step 2 — Attach Intents To Next-Step Packets

Files:

- `orchestrator/lib/next_step.py`
- `web/frontend/src/game/types.ts`
- `web/frontend/src/game/EventEngine.ts`
- tests: `tests/test_next_step.py`, `web/frontend/tests/test_event_engine.py`

Status: Done 2026-04-22.

Implementation:

- `build_next_step_packet()` reads queued intents relevant to the packet step.
- Add `queued_intents` to packet payload.
- Match rules:
  - `atom_id == step` applies directly.
  - `atom_id == null` applies globally.
  - `kind == note` may attach as discussion-only but should not block prompt application.
- EventEngine exposes `nextStepPacket.queuedIntents`.

Quality gate after Step 2:

- Replay at event N shows only intents known at event N.
- No frontend-derived packet supersedes backend packet.
- Test command:

```bash
uv run pytest -q tests/test_next_step.py web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
git diff --check
```

### Step 3 — Apply Prompt Intents At Context Assembly

Files:

- `orchestrator/lib/control.py`
- `orchestrator/lib/intents.py`
- role tests that cover prompt augmentation
- `tests/test_intents.py`

Status: Done 2026-04-22.

Implementation:

- Convert relevant queued `interject` / `intercept` / `reroute` intent payloads into prompt-context instructions.
- `build_operator_context(project_dir, phase)` returns both rendered context and consumed intent ids, or add a sibling helper if changing the return type is too risky.
- `append_operator_context()` emits `operator_intent_applied` through `state.events` only when an intent was actually included.
- Because `append_operator_context()` currently receives only `project_dir`, either:
  - add optional `events` / `step` metadata to call sites, or
  - perform terminal emission one layer up in each role wrapper after context is appended.

Preferred implementation:

- Add `consume_queued_intents(project_dir, phase)` in `orchestrator/lib/intents.py`.
- Return prompt lines and applied-event payloads.
- `append_operator_context(..., events=None)` emits if `events` is provided.
- Update opencode-backed roles to pass `self.state.events`.

Quality gate after Step 3:

- An intent targeting `implementation` appears in the coder prompt exactly once.
- `operator_intent_applied` has `applied_to=prompt_context` and an artifact/source ref.
- Re-running context assembly does not double-apply the same intent.
- Test command:

```bash
uv run pytest -q tests/test_intents.py tests/test_coder.py tests/test_reviewer.py tests/test_tester.py tests/test_deployer.py tests/test_architect_judge.py
git diff --check
```

Evidence 2026-04-22:

```bash
uv run pytest -q tests/test_intents.py tests/test_coder.py tests/test_reviewer.py tests/test_tester.py tests/test_deployer.py tests/test_architect_judge.py
# 99 passed
uv run pytest -q web/backend/tests/test_intents.py tests/test_next_step.py web/frontend/tests/test_event_engine.py
# 11 passed
./web/frontend/build.sh
# passed, dist/app.js 1,240,514 bytes
git diff --check
# clean
```

### Step 4 — Ignore Stale Or Unsupported Intents

Files:

- `orchestrator/lib/intents.py`
- `orchestrator/engine.py`
- tests: `tests/test_intents.py`, `tests/test_engine.py`

Status: Done 2026-04-22.

Implementation:

- At phase completion or before next packet emission, scan queued intents.
- If target step is already completed, emit `operator_intent_ignored` with `target_step_passed`.
- If kind is not supported for prompt application, emit `operator_intent_ignored` with `unsupported_kind`, unless it was handled by a different subsystem.
- Update JSONL status to `ignored`.

Quality gate after Step 4:

- Every queued intent becomes applied or ignored by the time its target step is passed.
- No intent receives two terminal outcomes.
- Test command:

```bash
uv run pytest -q tests/test_intents.py tests/test_engine.py
git diff --check
```

Evidence 2026-04-22:

```bash
uv run pytest -q tests/test_intents.py tests/test_engine.py
# 36 passed
uv run pytest -q tests/test_coder.py tests/test_reviewer.py tests/test_tester.py tests/test_deployer.py tests/test_architect_judge.py web/frontend/tests/test_event_engine.py
# 99 passed
./web/frontend/build.sh
# passed, dist/app.js 1,240,514 bytes
git diff --check
# clean
```

### Step 5 — Frontend Intent Lifecycle Fold

Files:

- `web/frontend/src/game/types.ts`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/tests/test_event_engine.py`

Status: Done 2026-04-22.

Implementation:

- Add snapshot fields:
  - `pendingIntents`
  - `appliedIntents`
  - `ignoredIntents`
- Fold `operator_intent` into pending.
- Fold `operator_intent_applied` and `operator_intent_ignored` out of pending and into terminal maps.
- Attach pending intents relevant to `nextStepPacket.step`.

Quality gate after Step 5:

- Replay scrub shows pending/applied/ignored state exactly as of event index.
- PWA can answer: "what did I submit, and what happened to it?"
- Test command:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
git diff --check
```

Evidence 2026-04-22:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py
# 7 passed
./web/frontend/build.sh
# passed, dist/app.js 1,245,195 bytes
git diff --check
# clean
```

### Step 6 — PWA Next-Step Sheet

Files:

- `web/frontend/src/game/GameShell.ts`
- possibly `web/frontend/src/game/SceneManager.ts`
- `web/frontend/tests/test_game_map.py`

Status: Done 2026-04-22.

Implementation:

- Bottom HUD uses `snapshot.nextStepPacket.title`, not local guessed workflow order.
- Tapping next-step opens a compact sheet using existing overlay/dock surfaces.
- Sheet shows:
  - step title and objective
  - why now
  - memory wake-up hash/ref
  - inputs/source refs
  - queued/applied/ignored intents for that step
  - compose action for `interject`
- Do not add a table or separate dashboard tab.

Quality gate after Step 6:

- First viewport answers: what next, why, memory/source refs, where to intervene.
- iPhone 375x812 does not overlap.
- Existing map tests confirm bundle contains next-step UI primitives.
- Test command:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
git diff --check
```

Evidence 2026-04-22:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
# 14 passed
./web/frontend/build.sh
# passed, dist/app.js 1,256,262 bytes
node --input-type=module <playwright visual harness>
# desktop: no sheet/HUD overlap, sheet within viewport, canvasSignal 100312
# mobile 393x852: no sheet/HUD overlap, sheet within viewport, canvasSignal 96573
git diff --check
# clean
```

### Step 7 — End-To-End Rehearsal

Files:

- integration tests as needed
- `project-management/STATUS.md`

Status: Done 2026-04-22.

Implementation:

- Run a dry-run/project fixture:
  - create project
  - receive next-step packet
  - post operator intent targeting next step
  - run phase
  - assert applied/ignored event
  - assert EventEngine replay fold matches lifecycle.

Quality gate after Step 7:

- No intent exits without terminal event.
- Raw event ledger can reconstruct next-step + intent lifecycle.
- PWA has enough state to render queued -> applied/ignored.
- Test command:

```bash
uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
git diff --check
```

Evidence 2026-04-22:

```bash
uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py web/frontend/tests/test_event_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 21 passed
./web/frontend/build.sh
# passed, dist/app.js 1,256,262 bytes
git diff --check
# clean
```

## Stop Conditions

Stop and fix before proceeding if any of these happen:

- A prompt consumes an operator intent without `operator_intent_applied`.
- An ignored intent lacks a reason.
- A UI view derives authoritative next step from local workflow order when a backend packet exists.
- A new event lacks event identity fields.
- A new surface looks like a dashboard table instead of a map/sheet/object interaction.
- Any secret-like payload appears in event logs, JSONL control files, prompt logs, or PWA state.

## First Delivery Recommendation

Start with Steps 1 and 2 only.

Reason:

- They make intents durable and attach them to the already-implemented next-step packet.
- They unblock PWA visibility before we touch prompt-injection semantics.
- They give us a clean testable checkpoint before Step 3 mutates role prompt construction.

Definition of first delivery done:

- [x] `POST /intents` returns a `client_intent_id`.
- [x] `.orchestrator/control/intents.jsonl` has one queued row.
- [x] The next `next_step_packet_created` event includes that queued intent when it targets the packet step.
- [x] EventEngine replay shows that queued intent attached to `nextStepPacket`.

Evidence 2026-04-22:

```bash
uv run pytest -q web/backend/tests/test_intents.py tests/test_intents.py tests/test_next_step.py web/frontend/tests/test_event_engine.py
# 13 passed
./web/frontend/build.sh
# passed, dist/app.js 1,240,514 bytes
git diff --check
# clean
```
