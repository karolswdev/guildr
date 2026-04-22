# PWA Narrative Replay And Intervention Surface

## Purpose

This document defines the next product layer for the Council PWA: a
game-grade narrative surface that lets the operator understand how a project
came to be, what just happened, what is about to happen next, and where to
intervene.

This is not filesystem time travel. The replay surface does **not** need to
restore the project directory to an old state or restart execution from an
arbitrary historical file snapshot. Replay means:

- reconstruct the project story from durable events,
- show highlights and consequences of recent work,
- expose the next slated workflow step,
- explain the context that will be sent into that step,
- let the operator inject intent before the step proceeds,
- preserve a discussion log that can itself be rendered as a replay file.

The PWA should feel like a tactical command room for a living build operation.
The user is not reading logs after the fact. They are watching a project form,
understanding the minds that shaped it, and nudging the run at meaningful
boundaries.

## Product Thesis

The current map is a spatial workflow graph. The next layer should make it a
story engine.

Every project needs three simultaneous views:

1. **Project Mythos**: what are we building, why, who is the founding team,
   what viewpoints are shaping the product, and what principles are driving
   choices?
2. **Recent Run Story**: what happened in the last few steps, what changed,
   what artifacts were created, what decisions were made, and what risks or
   open questions remain?
3. **Next Move Control**: what is about to run next, what context will be
   sent, what can the operator add, and where can that input be applied?

These are not separate dashboard tabs. They are layers over the same event
ledger and workflow graph.

## Design Principles

- **Replay is semantic, not archival.** Show the meaning of the run, not only
  chronological event payloads.
- **The default view starts with purpose.** Entering the PWA should reveal the
  project goal, founding team, active stance, current phase, and next action.
- **Intervention happens before motion.** The most useful operator moment is
  just before a meaningful step starts, gate opens, repair loop begins, or
  artifact moves into review.
- **Discussion is durable state.** Agent summaries, persona debates, operator
  notes, gate decisions, and intent outcomes must become events/artifacts that
  can be replayed later.
- **Agents can narrate, but events remain source of truth.** A summarizer
  agent may synthesize highlights, but the synthesis cites event ids,
  artifact refs, and step ids so it can be audited.
- **Game objects carry meaning.** Founders, artifacts, decisions, risks, and
  operator intents appear as bodies, trails, cards, or speech tails with
  clear rules.

## Existing Anchors

The design builds on existing surfaces:

- Backend event history: `GET /api/projects/{id}/events`
- Live stream: `GET /api/projects/{id}/stream`
- Workflow control: `GET/PUT /api/projects/{id}/control/workflow`
- Resume/control: `POST /api/projects/{id}/control/resume`
- Instructions: `POST /api/projects/{id}/control/instructions`
- Map intents: `POST /api/projects/{id}/intents`
- Persona synthesis: `POST /api/projects/{id}/control/personas/synthesize`
- Artifacts: `GET /api/projects/{id}/artifacts/{name}`
- Frontend folding: `EventEngine`
- Frontend shell: `GameShell`
- Three.js scene: `SceneManager`

The new layer should extend these contracts rather than invent a second state
system.

## Terminology

### Narrative Replay

A replayable presentation of events, artifacts, summaries, and decisions. It
answers "what happened and why does it matter?" It does not imply restoring
old filesystem state.

### Discussion Log

A durable sequence of project-facing conversation events. It includes persona
forum output, operator notes, agent narrative digests, gates, objections,
decisions, and next-step recommendations.

### DWA: Displayable Work Artifact

Working name for an agent-synthesized visual/narrative card shown in the PWA.
A DWA is a compact summary artifact created from recent events and artifacts.
It is suitable for display as a floating story object, focus-panel card, or
timeline highlight.

Examples:

- "The architect split the goal into one README-producing task."
- "Tester verified the evidence command and found no mismatch."
- "Reviewer approved with one note about deployment simplicity."
- "Next: deployment will receive REVIEW.md, env scan, and deploy config scan."

Each DWA must carry source refs so it can be traced back to events and files.

### Next-Step Packet

A structured preview of the next workflow step: role, objective, inputs,
artifacts, memory, prior decisions, operator intents, and the exact kind of
context that will be sent.

## Target First-Viewport Experience

When the user opens a project map, the first viewport should show:

- center: zero-g workflow map, framed around the active or next atom,
- upper region: compact project purpose and current run status,
- visible bodies: founding team / persona council near the discovery/plan
  cluster,
- active path: the last completed step and the next slated step connected by
  a highlighted transfer corridor,
- bottom HUD: next step, recent highlight count, cost, and replay/story entry,
- one-tap action: "Drop in" / "Nudge" / "Intercept" for the next step.

The first view should not default to a table, raw log, or generic progress
bar. It should answer:

- what are we building?
- who is shaping it?
- what just happened?
- what is about to happen?
- where can I intervene?

## Information Architecture

### 1. Project Mythos Layer

Purpose: orient the user before they inspect any event.

Data sources:

- `qwendea.md`
- workflow step `persona_forum.config.personas`
- `.orchestrator/memory/wake-up.md`
- persona forum artifacts/events
- operator instructions and project notes

PWA presentation:

- "Goal Core" body near the center of the map.
- "Founding Team" cluster near discovery/planning.
- Each persona is a selectable character/body with:
  - name,
  - role,
  - worldview,
  - concerns,
  - current stance,
  - last contribution,
  - disagreement/consensus markers.
- A small "Edit mind" or "Shape stance" action posts an operator intent or
  workflow/persona update.

Required backend model:

```json
{
  "type": "project_mythos_updated",
  "project_id": "p1",
  "goal": "Build a JSON formatter CLI",
  "founding_team": [
    {
      "id": "ux_advocate",
      "name": "UX Advocate",
      "role": "Product clarity",
      "stance": "Keep the CLI simple and verifiable",
      "concerns": ["No hidden network dependency"]
    }
  ],
  "source_refs": ["qwendea.md", "workflow:persona_forum"]
}
```

Implementation note:

The first version can compute this on demand from existing files and emit
`project_mythos_updated` only when personas are synthesized or edited. Later,
it can become a normal event emitted during project creation and persona forum
execution.

### 2. Recent Story Layer

Purpose: convert the last few events into a useful, memorable summary.

This is where the DWA lives.

Inputs:

- last N durable events,
- phase logs,
- raw-io/usage summaries,
- artifact refs,
- sprint-plan/task status,
- gate decisions,
- operator intents.

Output:

```json
{
  "type": "narrative_digest_created",
  "digest_id": "dwa_01HQ...",
  "window": {
    "from_event_id": "evt_a",
    "to_event_id": "evt_f",
    "event_count": 17
  },
  "title": "The build passed its first verification loop",
  "summary": "Coder created README.md, Tester verified `ls README.md`, and Reviewer approved the task.",
  "highlights": [
    {
      "kind": "artifact_created",
      "text": "README.md was created by the implementation step.",
      "refs": ["event:evt_c", "artifact:README.md"]
    },
    {
      "kind": "evidence_passed",
      "text": "The evidence command completed successfully.",
      "refs": ["event:evt_d", "artifact:TEST_REPORT.md"]
    }
  ],
  "open_questions": [],
  "risks": [],
  "next_step_hint": {
    "step": "deployment",
    "why": "Review has approved the work and deployment planning is next."
  },
  "source_event_ids": ["evt_a", "evt_b", "evt_c", "evt_d", "evt_e", "evt_f"],
  "artifact_refs": ["README.md", "TEST_REPORT.md", "REVIEW.md"]
}
```

PWA presentation:

- A DWA appears as a small story satellite near the relevant atom cluster.
- On tap, it opens a story card:
  - title,
  - 2-4 highlights,
  - artifact thumbnails/previews,
  - "why this matters",
  - "next move",
  - source refs.
- In replay mode, DWA cards appear at the point they were created.

Agent role:

Add a `narrator` or `scribe` role that runs between major steps or after a
configurable event count. It does not mutate project files. It reads a bounded
event/artifact packet and writes:

- `.orchestrator/narrative/digests/{digest_id}.json`
- optionally `.orchestrator/narrative/digests/{digest_id}.md`
- event: `narrative_digest_created`

The role should be cheap and bounded. It should prefer a local or small model
unless the operator opts into richer narration.

### 3. Next-Step Control Layer

Purpose: make the upcoming step inspectable and editable before it runs.

The PWA should always know the "next slated step":

- if a run is active: next enabled workflow step not done/waiting/error,
- if a gate is open: the gate is the next intervention target,
- if replay/history: next step after the scrub index,
- if idle: first enabled incomplete step or "start run".

Next-step packet schema:

```json
{
  "type": "next_step_packet_created",
  "packet_id": "next_01HQ...",
  "step": "implementation",
  "title": "Implementation",
  "role": "coder",
  "objective": "Create README.md according to Task 1.",
  "why_now": "Architect plan is approved and task packets are ready.",
  "inputs": [
    { "kind": "artifact", "ref": "sprint-plan.md", "label": "Sprint plan" },
    { "kind": "artifact", "ref": "phase-files/task-001-implement.md", "label": "Task packet" },
    { "kind": "memory", "ref": ".orchestrator/memory/wake-up.md", "label": "Wake-up packet" },
    { "kind": "operator_context", "ref": ".orchestrator/control/instructions.jsonl", "label": "Queued operator notes" }
  ],
  "context_preview": [
    "Goal: Build the smallest README-producing project.",
    "Task: bootstrap",
    "Evidence: Run `ls README.md`"
  ],
  "intervention_options": ["interject", "intercept", "reroute", "skip"],
  "source_refs": ["workflow:implementation", "artifact:sprint-plan.md"]
}
```

PWA presentation:

- The next atom glows with a distinct "ready" outline.
- The corridor from last completed step to next step is highlighted.
- The HUD shows: `Next: Implementation`.
- Tapping opens the Next-Step Sheet:
  - objective,
  - context preview,
  - inputs,
  - pending operator notes,
  - "Drop in a suggestion" composer,
  - optional "hold before this step" switch.

Operator actions:

- **Nudge**: append an instruction for the next role.
- **Intercept**: hold at the next boundary and require operator approval.
- **Shape**: adjust workflow/persona/task direction.
- **Note**: add commentary to the discussion log without changing execution.

Events:

```json
{
  "type": "operator_intent",
  "kind": "interject",
  "atom_id": "implementation",
  "payload": {
    "instruction": "Keep the README minimal and include a usage example.",
    "scope": "implementation",
    "source": "map_next_step_sheet"
  }
}
```

Follow-up events should be added when an intent is consumed:

```json
{
  "type": "operator_intent_applied",
  "client_intent_id": "intent_123",
  "atom_id": "implementation",
  "applied_to": "prompt",
  "artifact_refs": [".orchestrator/control/instructions.jsonl"]
}
```

Without `operator_intent_applied`, the PWA can only show that the user
submitted intent, not whether it affected the run.

### 4. Discussion Log Layer

Purpose: make the project history socially and intellectually legible.

The discussion log should be a durable, replayable project artifact. It is not
only chat. It includes:

- user notes,
- persona statements,
- agent summaries,
- disagreements,
- gate decisions,
- reviewer verdicts,
- narrator DWA summaries,
- operator intent submissions and outcomes.

Storage:

- event ledger remains canonical for event order,
- `.orchestrator/discussion/log.jsonl` can be a projection optimized for
  direct reading,
- `.orchestrator/discussion/highlights.jsonl` can store narrator-selected
  moments.

Core event types:

```json
{
  "type": "discussion_entry_created",
  "entry_id": "disc_01HQ...",
  "speaker": {
    "kind": "operator|persona|role|system|narrator",
    "id": "ux_advocate"
  },
  "step": "persona_forum",
  "atom_id": "persona_forum",
  "text": "The CLI should optimize for predictable output over clever defaults.",
  "mood": "concerned",
  "stance": "simplicity",
  "source_refs": ["event:evt_123", "artifact:personas.json"]
}
```

```json
{
  "type": "discussion_highlight_created",
  "highlight_id": "hi_01HQ...",
  "title": "Simplicity became a product constraint",
  "summary": "The founding team aligned that predictable output matters more than rich formatting options.",
  "source_entry_ids": ["disc_a", "disc_b", "disc_c"],
  "impact": {
    "workflow_steps": ["architect", "implementation"],
    "artifact_refs": ["sprint-plan.md"]
  }
}
```

PWA presentation:

- Speech tails around persona/role bodies.
- A "Council Memory" lens showing the last 3-5 meaningful statements.
- Tap a persona to inspect their evolving stance and decisions they
  influenced.
- Tap a DWA/highlight to jump to related atoms and artifacts.

## Default PWA Screen: Proposed Layout

### Global View

The first screen should show:

```text
Top safe area:
  [Back] [Project goal: compact one-line] [Live/Replay]

Canvas:
  - Goal Core body
  - Founding Team cluster
  - Workflow atoms as current zero-g map
  - last step and next step highlighted
  - recent DWA story satellite near the active path

Bottom HUD:
  [Next: Implementation] [Story: 3] [Cost] [Loop dots]

Primary gesture:
  Tap next atom -> Next-Step Sheet
  Tap story satellite -> Recent Story Card
  Tap founder/persona -> Persona Mind Sheet
```

### Object View

When an atom is selected:

- left/center canvas focuses the atom,
- near it float:
  - incoming context bodies,
  - outgoing artifact body,
  - recent DWA summary,
  - operator intent packet if one exists.
- bottom sheet shows:
  - what this step does,
  - what it consumed,
  - what it produced,
  - what it will do next,
  - actions to nudge/intercept/shape.

### Story View

Story view is not a separate route initially. It is a lens:

- freezes camera around recent path,
- dims unrelated atoms,
- shows DWA cards in chronological order,
- timeline scrubber moves through digest cards rather than raw events,
- each card can expand to source events/artifacts.

## Event Architecture

### Event Categories

Existing:

- `phase_start`
- `phase_done`
- `phase_error`
- `phase_retry`
- `gate_opened`
- `gate_decided`
- `usage_recorded`
- `loop_entered`
- `loop_blocked`
- `loop_repaired`
- `loop_completed`
- `operator_intent`
- `memory_status`
- `memory_refreshed`

Proposed additions:

- `project_mythos_updated`
- `discussion_entry_created`
- `discussion_highlight_created`
- `narrative_digest_created`
- `next_step_packet_created`
- `operator_intent_applied`
- `operator_intent_ignored`
- `artifact_preview_created`
- `persona_stance_updated`

### Folding Rules

`EventEngine` should grow additional folded state:

```ts
type NarrativeSnapshot = {
  mythos: ProjectMythos | null;
  discussion: DiscussionEntry[];
  highlights: DiscussionHighlight[];
  digests: NarrativeDigest[];
  latestDigestByAtom: Record<string, NarrativeDigest>;
  nextStepPacket: NextStepPacket | null;
  pendingIntents: OperatorIntent[];
  appliedIntents: Record<string, OperatorIntentOutcome>;
};
```

`EngineSnapshot` should include:

```ts
{
  narrative: NarrativeSnapshot;
}
```

Fold behavior:

- `project_mythos_updated` replaces current mythos snapshot.
- `discussion_entry_created` appends to discussion.
- `discussion_highlight_created` appends to highlights.
- `narrative_digest_created` appends and indexes by related atom/source step.
- `next_step_packet_created` replaces current packet when newer.
- `operator_intent` appends to pending intents.
- `operator_intent_applied` moves intent from pending to applied.
- `operator_intent_ignored` moves intent from pending to applied with ignored
  status and reason.

Replay behavior:

- Scrubbing to event index N folds narrative events only through N.
- Story cards shown at replay point are the digests/highlights available at
  that point.
- The next-step packet in replay mode is the packet known at that point, not a
  recomputation from current workflow.

Live behavior:

- If no `next_step_packet_created` exists yet, frontend can derive a temporary
  next step from atom states and workflow.
- Backend/agent-generated packet supersedes the temporary one when available.

## Agent Design: Narrator / Scribe

### Role

The Narrator turns recent events into DWAs, discussion highlights, and
next-step packet text. It does not decide workflow. It explains workflow.

### When It Runs

Initial triggers:

- after `phase_done`,
- after `gate_decided`,
- after `phase_error`,
- after `operator_intent`,
- before a step that is about to run if no recent packet exists.

To avoid token waste, debounce:

- no more than once per phase,
- no more than once per 10 events unless a gate/error/intent occurs,
- skip if the event window contains no user-facing change.

### Input Packet

The orchestrator should construct a bounded packet:

```json
{
  "project_goal": "...",
  "workflow": [{ "id": "implementation", "title": "Implementation", "state": "done" }],
  "recent_events": [{ "event_id": "...", "type": "...", "step": "..." }],
  "recent_artifacts": [
    { "ref": "sprint-plan.md", "excerpt": "..." },
    { "ref": "TEST_REPORT.md", "excerpt": "..." }
  ],
  "open_gates": [],
  "pending_intents": [],
  "next_step": { "id": "deployment", "title": "Deployment" }
}
```

### Output Contract

The Narrator must return JSON:

```json
{
  "digest": {
    "title": "...",
    "summary": "...",
    "highlights": [],
    "risks": [],
    "open_questions": [],
    "source_event_ids": [],
    "artifact_refs": []
  },
  "discussion_entries": [],
  "next_step_packet": {
    "step": "...",
    "objective": "...",
    "why_now": "...",
    "inputs": [],
    "context_preview": [],
    "intervention_options": []
  }
}
```

Validation:

- all source event ids must exist in the packet,
- all artifact refs must be safe relative project paths,
- summary length capped,
- no secrets,
- no claims without a source ref unless marked as inference.

### Runtime

The narrator should be implemented as another `SessionRunner` role:

- role name: `narrator`
- tool access: read-only, no shell in v1
- model route: cheap/local by default
- audit: `emit_session_audit`
- artifacts:
  - `.orchestrator/narrative/digests/*.json`
  - `.orchestrator/discussion/log.jsonl`
- events:
  - `narrative_digest_created`
  - `discussion_entry_created`
  - `next_step_packet_created`

## Backend Work Items

### B1. Narrative Data Types

Add typed schemas for:

- `ProjectMythos`
- `DiscussionEntry`
- `DiscussionHighlight`
- `NarrativeDigest`
- `NextStepPacket`
- `OperatorIntentOutcome`

Acceptance:

- invalid event payloads rejected by event validation,
- all refs are path-safe,
- all narrative events include `event_id`, `schema_version`, `run_id`, `ts`,
  and `type`.

### B2. Discussion Log Projection

Add helpers:

- `orchestrator/lib/discussion.py`
- append discussion entries,
- write projection JSONL,
- emit `discussion_entry_created`.

Acceptance:

- operator notes and persona statements can become discussion entries,
- projection can be rebuilt from events,
- secrets are scrubbed through existing scrub helpers.

### B3. Narrator Role

Add:

- `orchestrator/roles/narrator.py`
- `orchestrator/roles/narrator_dryrun.py`
- prompt under `orchestrator/roles/prompts/narrator/generate.txt`
- engine hook after major step events or as explicit workflow phase.

Acceptance:

- dry-run produces one DWA and one next-step packet,
- live/config path can route `narrator` through opencode,
- audit rows exist for narrator sessions,
- invalid narrator JSON fails loudly and does not corrupt event ledger.

### B4. Next-Step Packet Generator

Add deterministic fallback generator:

- computes next step from workflow + atom states,
- gathers obvious artifact refs,
- includes pending operator instructions,
- emits `next_step_packet_created` before a step starts when possible.

Acceptance:

- PWA always has a next step in idle/live/history,
- packet is replayable from events,
- packet can be generated without LLM.

### B5. Intent Outcome Events

Extend control paths so submitted intents get outcomes:

- `operator_intent_applied`
- `operator_intent_ignored`

Acceptance:

- when `append_operator_context` consumes an instruction, it emits/applies an
  outcome or marks it consumed in a durable way,
- PWA can distinguish "queued" from "used in prompt".

### B6. Persona/Mythos Events

When personas are synthesized or edited:

- emit `project_mythos_updated`,
- emit one `discussion_entry_created` per meaningful persona statement,
- persist persona stance changes.

Acceptance:

- default PWA can render goal + founding team without reading raw config,
- persona edits appear in history.

## Frontend Work Items

### F1. Extend EventEngine Narrative Folding

Add `NarrativeSnapshot` to `EngineSnapshot`.

Acceptance:

- loads narrative events from history,
- dedupes by `event_id`,
- scrub mode rewinds narrative state,
- live SSE appends narrative objects without full reload.

### F2. Project Mythos Header

Default map view shows:

- project goal,
- founding team count,
- active stance/consensus,
- current run status.

Acceptance:

- fits mobile portrait,
- does not occlude map interaction,
- skeleton state when mythos missing,
- tap opens Mythos Sheet.

### F3. Founding Team / Persona Mind Sheet

Render persona bodies near discover/plan cluster.

Sheet includes:

- persona identity,
- stance,
- concerns,
- last statements,
- decisions influenced,
- "shape stance" composer.

Acceptance:

- personas are selectable,
- stance edits create operator intent or persona update,
- speech tails render for recent discussion entries.

### F4. Recent Story Satellites

Render DWA objects from `narrative_digest_created`.

Acceptance:

- latest digest visible near related atom,
- tap opens digest card,
- digest card links to artifacts/source events,
- old digests fade into story trail on mobile.

### F5. Next-Step Sheet

Add a persistent bottom-HUD "Next" control.

Sheet includes:

- next step title,
- why now,
- objective,
- context preview,
- inputs,
- pending/applied operator intents,
- nudge/intercept/shape/note actions.

Acceptance:

- available before run starts,
- updates as events arrive,
- in replay mode shows historical next packet,
- no raw JSON required for normal use.

### F6. Intent Lifecycle Visualization

Submitted intents become visible packets.

States:

- queued,
- applied,
- ignored,
- superseded.

Acceptance:

- submitting from compose dock creates immediate visible packet,
- `operator_intent_applied` changes packet state,
- packet connects to target atom/path,
- ignored intent explains why.

### F7. Story Replay Lens

Add lens toggle over the existing timeline.

Modes:

- raw event scrub,
- story digest scrub.

Acceptance:

- digest cards are ordered by source window,
- selecting a digest dims unrelated atoms,
- source event/artifact refs can be inspected,
- no filesystem restoration implied.

### F8. Artifact Preview Cards

Turn artifact refs into displayable previews.

Acceptance:

- fetch artifact text from existing artifact route,
- preview bounded to safe size,
- markdown/source files shown as readable snippets,
- artifact body anchors to producing atom.

## Visual Grammar

### Goal Core

The project goal is a central low-frequency body. It is not a card. It should
feel like the gravity source of the map.

Visual rules:

- calm glow,
- no aggressive pulse,
- tap opens project brief,
- recent changes to goal create small ripples.

### Founding Team

Personas orbit the goal/discovery cluster.

Visual rules:

- each persona has a distinct body,
- speech tails point to the atom or decision they influenced,
- disagreement appears as tension lines,
- consensus appears as merged soft trails.

### DWA Story Satellites

Digest objects orbit the atom cluster they summarize.

Visual rules:

- recent digest is bright and readable,
- older digests shrink/fade into a trail,
- digest source refs appear as thin tethers to atoms/artifacts,
- tap expands into a story card.

### Next-Step Beam

The path to the next slated step is always visible.

Visual rules:

- one highlighted corridor only,
- last completed step glows softly,
- next step has a ready outline,
- pending operator intent attaches to the beam as a packet.

### Intent Packet

Operator input must become an object immediately.

Visual rules:

- created at screen edge or operator/avatar position,
- travels to target atom/path,
- queued packet orbits until applied,
- applied packet merges into the atom prompt/context,
- ignored packet dims and exposes reason.

## UX Copy Guidelines

Use short, operational text:

- "Next: Implementation"
- "Why now: plan approved"
- "Context: sprint plan, task packet, wake-up memory"
- "Drop in before this step"
- "Queued for coder"
- "Used in prompt"
- "Ignored: step already completed"

Avoid:

- "Here are the features of this UI"
- long explanations in the map layer,
- raw event jargon as primary text,
- philosophical labels where operational labels are clearer.

## Implementation Slices

### Slice 1: Deterministic Next-Step Sheet

Goal: make the PWA immediately useful for intervention.

Tasks:

1. Add frontend-derived next-step selector in `EventEngine` or `GameShell`.
2. Add bottom HUD `Next: <step>` control.
3. Add Next-Step Sheet with objective, state, and nudge composer.
4. Post nudge through existing `/intents` route.
5. Show pending intent packet locally from `operator_intent`.

No narrator agent required.

Evidence:

- frontend test proves next step changes after phase events,
- map bundle contains next-step sheet,
- manual mobile screenshot shows no overlap.

### Slice 2: Discussion Log Events

Goal: make operator/persona/project discussion durable.

Tasks:

1. Add `discussion_entry_created` event schema.
2. Convert map notes into discussion entries.
3. Convert persona synthesis output into discussion entries.
4. Add EventEngine folding for discussion entries.
5. Add Mythos Sheet with recent discussion.

Evidence:

- backend tests for event validation and secret scrub,
- frontend folding test for replay/scrub.

### Slice 3: DWA Digest Without LLM

Goal: ship story satellites from deterministic rules first.

Tasks:

1. Create deterministic digest generator for phase/gate clusters.
2. Emit `narrative_digest_created`.
3. Fold digests into EventEngine.
4. Render latest digest card/satellite.

Evidence:

- fixture events produce digest,
- PWA displays digest in replay and live mode.

### Slice 4: Narrator Agent

Goal: upgrade deterministic digest into richer synthesis.

Tasks:

1. Add `narrator` SessionRunner role.
2. Build bounded event/artifact packet.
3. Validate narrator JSON.
4. Emit digest/discussion/next-step events.
5. Add dry-run narrator.

Evidence:

- unit tests for prompt packet and JSON validation,
- fake-opencode integration covering narrator session,
- no secrets in output.

### Slice 5: Intent Outcomes

Goal: close the loop between "I dropped this in" and "the system used it."

Tasks:

1. Assign stable `client_intent_id` from PWA.
2. Persist pending intent.
3. Mark consumed when prompt/context assembly uses it.
4. Emit `operator_intent_applied` or `operator_intent_ignored`.
5. Render packet lifecycle.

Evidence:

- backend test shows intent moves queued -> applied,
- frontend test shows packet state update.

### Slice 6: Persona Mind Editing

Goal: let the operator shape the founding team.

Tasks:

1. Emit mythos/persona events from synthesis route.
2. Add Persona Mind Sheet.
3. Add stance-edit action.
4. Persist stance update into workflow config or persona artifact.
5. Show stance changes in discussion log.

Evidence:

- persona update survives reload,
- discussion history shows before/after.

## Acceptance Criteria For The Whole Layer

- Opening a project shows goal, founding team, current status, and next step.
- The operator can add a suggestion before the next step from the map.
- Submitted suggestions become visible objects with lifecycle state.
- Recent events produce at least one readable story/DWA card.
- Story cards cite source event ids and artifact refs.
- Persona/founding-team statements are durable discussion entries.
- Replay scrub can show story and discussion state as of the selected event.
- No raw event table is required to understand the last few meaningful things.
- All new narrative state is derivable from events or documented projection
  files.
- Mobile portrait remains the primary layout.

## Open Questions

- Should narrator run as a workflow phase, an engine sidecar after phases, or
  both?
- How often should DWA digest generation run during long opencode sessions?
- Should persona stance edits be immediate config changes or queued operator
  intents consumed by the next persona/forum pass?
- Should next-step packets be persisted for every step or generated only at
  boundaries where the operator can intervene?
- Should discussion projection files be authoritative artifacts or rebuildable
  caches from events?

## Recommended First Build

Build Slice 1 and Slice 2 first.

Reason:

- They immediately improve usability.
- They use existing `/events`, `/intents`, workflow, and persona routes.
- They do not require a new LLM role.
- They establish the event schema that the narrator agent can later enrich.

After that, add deterministic DWA digests before adding an LLM narrator. This
keeps the product honest: the story layer works from durable facts first, then
gets more expressive with model synthesis.
