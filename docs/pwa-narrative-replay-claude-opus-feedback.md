# Claude Opus Feedback: PWA Narrative Replay And Intervention

Captured: 2026-04-21

Command shape:

```bash
claude --model opus -p --no-session-persistence --tools Read,Grep,Glob --max-budget-usd 2 "<review prompt>"
```

Scope requested:

- `project-management/AGENT_ONBOARDING.md`
- `project-management/DIRECTION_GUARDRAILS.md`
- `docs/srs-council-engine.md`
- `docs/ux-interaction-model.md`
- `docs/spatial-flow-universe-design.md`
- `docs/pwa-narrative-replay-and-intervention-design.md`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/backend/routes/intents.py`
- `web/backend/routes/control.py`
- `web/backend/routes/events.py`

## Review

Reviewer: external, product + architecture

Scope: `AGENT_ONBOARDING.md`, `DIRECTION_GUARDRAILS.md`,
`srs-council-engine.md`, `ux-interaction-model.md`,
`spatial-flow-universe-design.md`,
`pwa-narrative-replay-and-intervention-design.md`, `EventEngine.ts`,
`GameShell.ts`, `SceneManager.ts` (not opened; reasoning below uses its
declared contracts), `routes/intents.py`, `routes/control.py`,
`routes/events.py`.

## 1. Does the design coherently advance the vision?

**Directionally yes, but with a real internal tension that is not resolved in
writing.**

Strengths:

- The narrative-replay doc is exactly the right re-framing. Explicitly stating
  that replay is semantic reconstruction, not filesystem time travel, kills
  the single biggest product trap: confusing replay with rollback. That
  sentence alone is worth the document.
- The three simultaneous views - Mythos, Recent Story, Next Move - map cleanly
  onto the user's ask: goal, founding-team minds, recent digests/DWAs, next
  step plus intervention. It is the right information architecture for an
  operator surface.
- The event ledger, with required `event_id`, `schema_version`, and `run_id`,
  is load-bearing in the right way: it is a join-key system, and folding it in
  `EventEngine` is the correct seam.
- `intents.py`, `control.py`, and `EventEngine` already implement most of the
  plumbing needed for Slice 1: deterministic Next-Step plus compose-dock
  intent. The lift to usable narrative surface is smaller than the docs imply.
- The design is internally consistent on mobile-first and on refusing to
  devolve into a dashboard. `DIRECTION_GUARDRAILS.md` is short and enforceable.

Where coherence fractures:

- **Two design vocabularies are running side-by-side.**
  `spatial-flow-universe-design.md` wants actors, orbits, speech tails,
  artifact accretion, and an animated universe.
  `pwa-narrative-replay-and-intervention-design.md` wants readable story
  cards, DWAs, Mythos headers, and a Next-Step sheet. These are not the same
  product. The universe doc is "game"; the narrative doc is "command room."
  The vision blurb lands squarely between them, and nothing in the repo states
  which wins when they collide. A founding-team persona mind in the narrative
  doc is a bottom sheet with a text composer; in the universe doc it is an
  orbiting astronaut body with speech tails. That is a single decision the
  team has not made.
- **SRS section 9 still enumerates ten screens** - Mission Control, Replay
  Viewer, Economics, Memory Browser, Workflow Editor, and so on. That reads as
  "dashboard with tabs," which directly contradicts
  `DIRECTION_GUARDRAILS.md`. The SRS should be rewritten so screens are lenses
  over one map, not peer routes.
- **Nothing in current code implements Mythos, DWA, or Next-Step packets.**
  `EventEngine.applyFold` handles phase/gate/usage/loop/memory only. There is
  no `NarrativeSnapshot`, no `nextStepPacket`, and no `pendingIntents`.
  `GameShell` already has Shape/Nudge/Intercept compose, but the operator
  cannot see the target context they are intercepting. The vision is
  documented; the code is one level below it.

Bottom line: the design advances the vision on paper, but the paper is split
in two and the code has not started catching up on the narrative half.

## 2. Missing Product And Architecture Pieces

### Product

- **Intervention feedback loop.** Today `/intents` emits `operator_intent` and
  returns. There is no `operator_intent_applied` or `operator_intent_ignored`
  event, no projection of what the prompt actually contained, and no visible
  receipt that the nudge reached the role. Without this, the operator is
  typing into a suggestion box that may or may not matter. This is the single
  highest-leverage gap.
- **Context that will be sent preview.** The vision explicitly asks for it.
  Nothing in `control.py`, `intents.py`, or `EventEngine` exposes the composed
  prompt packet for the next step. The Next-Step Packet schema is drafted in
  the narrative doc, but there is no backend endpoint such as
  `GET /projects/{id}/next-step` and no event emitter.
- **Persona stance as durable state.** `synthesize_personas` regenerates
  personas from `qwendea.md` each call and persists via `_persist_personas`.
  There is no `persona_stance_updated` event, no discussion-entry emission,
  and no stance history. Editing a persona's mind is undefined behavior right
  now.
- **DWA producer, even deterministic.** Slice 3 of the narrative doc,
  deterministic digests, should precede the narrator agent and does not exist.
  A rules-based digest-on-phase-done would be roughly 100 lines and
  immediately improve the map.
- **Discussion log projection.** `.orchestrator/discussion/log.jsonl` and the
  narrator-written `highlights.jsonl` are specified but absent.
- **Artifact preview route for text snippets.** The narrative doc relies on
  artifact previews anchored to atoms; `ArtifactAccretion` and
  `ContentPreviewLayer` are aspirational.
- **Mythos composition rule.** The first viewport is supposed to show goal,
  founding team, and active stance, but there is no single resolver that
  merges `qwendea.md`, workflow `persona_forum.config`, and wake-up packet
  into a `ProjectMythos`. Each surface will have to invent it.

### Architecture

- **No narrative event validation.** `events.py` uses `validate_event` with
  `require_run_id=True`. The new event types - `project_mythos_updated`,
  `discussion_entry_created`, `narrative_digest_created`,
  `next_step_packet_created`, `operator_intent_applied` - need schema
  validators or they will pollute the ledger silently. Given the existing
  `event_schema.py` stance, this must be done deliberately.
- **No `client_intent_id` lifecycle.** `intents.py` accepts it, passes it
  through, and then nothing consumes it. Without server-side persistence of
  the intent in pending state, the PWA cannot render queued -> applied ->
  ignored packet states.
- **`EventEngine` has no narrative folding surface.** Adding
  `NarrativeSnapshot` is straightforward, but the class has grown linearly:
  phase, usage, budget, loop, and memory branches are all inline. Before
  adding five more branches, fold logic should be refactored into a
  `FoldRegistry` or per-type handler map, or it becomes a maintenance hazard.
- **No event pagination or cursor.** `events.py` reads the entire JSONL every
  request and validates line-by-line. At 5k events this is already expensive;
  for replay UX scrubbing on mobile it will get worse. Needs a tail-read plus
  offset cursor.
- **SSE transport is fragile.** `EventEngine.connect()` has no real backoff, no
  last-event-id resume, no reconciliation beyond `seenEventIds`. Long SSE
  disconnects risk duplication or gaps.
- **Narrator runtime.** The narrator role is specified as a `SessionRunner`.
  The H6 opencode migration is the right substrate, but nothing explains how
  its debouncing hook lives relative to engine phase boundaries. "Engine
  sidecar vs workflow phase" is listed as an open question; it is actually a
  load-bearing architectural decision.
- **Scope collision with `spatial-flow-universe-design.md`.** That doc
  introduces multiple new frontend modules: `FlowDirector`,
  `ContentPreviewLayer`, `SpeechTailLayer`, `ArtifactAccretion`,
  `LoopClusterLayout`, `ModelCatalog`, `CharacterActor`,
  `AnimationDirector`, `GhostTether`. The narrative doc introduces parallel
  concerns: `MythosHeader`, `NextStepSheet`, `DWASatellite`,
  `PersonaMindSheet`. No one has reconciled the module list; there is risk of
  two overlapping subsystems that both want to own the same world-anchored DOM
  overlay.

## 3. Risks And Traps

1. **Vision drift into decoration.** `spatial-flow-universe-design.md` is
   beautifully written and easy to over-invest in. Astronaut animations,
   orbital parameters, comet speech tails - none of these answer the
   operator's question: what is about to happen and what can I change? Risk:
   months of flow-particle polish with no improvement in operational
   usefulness.
2. **Narrative digest credibility.** A narrator LLM that summarizes events can
   lie. Even with `source_event_ids` required, there is no automated check
   that summary claims are grounded. First user trust failure kills the
   feature. Start deterministic; only layer LLM narration on top once the JSON
   schema is enforced and the UI never shows a claim without a clickable
   source ref.
3. **Intent that disappears.** If the operator drops in a suggestion and the
   map shows no receipt, the product instantly reads as a fake dashboard with
   a comment box. This silently erodes trust. Ship intent outcomes before the
   narrator.
4. **Replay semantics ambiguity.** Narrative replay is well-defined in the new
   doc, but `scrubTo` still folds all events, including cost and atom state. If
   a persona edit happened at event 400 and the user scrubs to 200, should the
   map show the old persona stance or the current one? Today the answer is
   old, which is correct. But a single-state Mythos Header may show current.
   Needs an explicit rule.
5. **Dashboard relapse.** SRS sections still list tabular surfaces as peer
   screens. The easy path is to keep them. The correct path is to retire or
   re-cast each as a lens on the map.
6. **Mobile vs density conflict.** DWA satellites, story trail, speech tails,
   flow particles, Mythos header, cost ring, loop dots, compose dock: at
   iPhone portrait this is already over budget visually. The docs say at most
   one primary readable preview per focused cluster, but do not define the
   prioritization algorithm. Without a `VisualPriorityStack`, the scene will
   become noise under load.
7. **Workflow/persona edit concurrency.** `synthesize_personas` and
   `put_workflow` both mutate durable state without event emission. An
   operator stance edit can race a narrator digest that references the old
   stance. Need events-as-source-of-truth discipline here.
8. **Narrator cost.** If narrator runs after every `phase_done`,
   `gate_decided`, `phase_error`, and `operator_intent`, a flaky provider with
   retries and intent injections can emit many narrator runs for one atom.
   Debounce must be per-run, per-atom, and token-budgeted.

## 4. Concrete Recommendations

### 4.1 Event Schema

Lock these in `event_schema.py` before any UI work:

```text
narrative_digest_created {
  event_id, schema_version=1, ts, type, run_id,
  digest_id: ULID,
  window: { from_event_id, to_event_id, event_count },
  title, summary, highlights[],
  source_event_ids[], artifact_refs[],
  next_step_hint?: { step, why }
}

next_step_packet_created {
  event_id, schema_version=1, ts, type, run_id,
  packet_id: ULID,
  step, role, title, objective, why_now,
  inputs[] (kind in artifact|memory|operator_context|decision, ref, label),
  context_preview[] (string, <=200 chars each, <=8 lines),
  intervention_options[] (subset of IntentKind),
  source_refs[]
}

operator_intent update:
  require client_intent_id server-side.
  Mint ULID if absent and echo back.

operator_intent_applied {
  event_id, schema_version=1, ts, type, run_id,
  client_intent_id, atom_id,
  applied_to: "prompt" | "workflow" | "persona" | "note",
  artifact_refs[]
}

operator_intent_ignored {
  event_id, schema_version=1, ts, type, run_id,
  client_intent_id, atom_id, reason
}

discussion_entry_created {
  event_id, schema_version=1, ts, type, run_id,
  entry_id, speaker: { kind, id }, step, atom_id,
  text, stance?, mood?, source_refs[]
}

project_mythos_updated {
  event_id, schema_version=1, ts, type, run_id,
  goal, founding_team[], source_refs[]
}

persona_stance_updated {
  event_id, schema_version=1, ts, type, run_id,
  persona_id, stance, concerns[], source_refs[]
}
```

Rules:

- Every narrative event must carry `source_event_ids` or `source_refs`
  (path-safe). Reject otherwise. This is the credibility contract.
- Narrative events do not carry cost or usage fields; they are computed
  projections.
- Validation enforces `context_preview` caps to prevent narrator essays from
  leaking into the ledger.

### 4.2 Backend

- `GET /api/projects/{id}/next-step`: deterministic packet from workflow,
  atoms, and pending intents. Always available. Emits
  `next_step_packet_created` when the value changes.
- `GET /api/projects/{id}/mythos`: merges `qwendea.md`, workflow persona
  config, and latest persona stances. Returns the same shape as the event.
- `POST /api/projects/{id}/intents`: mint `client_intent_id` if absent,
  persist to `.orchestrator/control/intents.jsonl` with status `queued`, emit
  `operator_intent` with the id.
- `orchestrator/lib/control.append_instruction`: when an instruction is
  consumed into a prompt, emit `operator_intent_applied` with
  `applied_to="prompt"` and artifact refs. If a role starts without consuming
  an applicable queued intent, emit `operator_intent_ignored` with reason.
- `GET /api/projects/{id}/events`: add `?after_event_id=` cursor and
  `?tail=N` mode; stop re-reading the whole JSONL per request.
- Stream: use `event: message` and `id: <event_id>` so `EventSource` can resume
  with `Last-Event-ID`.

### 4.3 Frontend

- Refactor `EventEngine.applyFold` into a dispatch map keyed by `type`. Add
  `NarrativeSnapshot` as a new folded field, behind the same scrub semantics.
- Add `EventEngine.currentNextStepPacket()` that either returns the last
  `next_step_packet_created` at or before the replay index, or a
  client-computed fallback from workflow and atom states. This gives Slice 1
  behavior without backend changes.
- `GameShell`: add a persistent `Next:` chip to `bottomHud` on the left,
  separate from `focus-active`. Tap opens Next-Step Sheet. Long-press the
  active atom also opens it. The existing action ring should be a secondary
  entry point, not the only one.
- Ship a `NextStepSheet` DOM panel with objective, why now, inputs, context
  preview, pending intent chips, compose textarea, and Nudge/Intercept/Shape
  buttons. Reuse the `/intents` POST already wired in `queueCompose`.
- Render pending intents as DOM chips anchored to the atom with a
  world-to-screen projection each frame. Intent lifecycle: queued blue pulse,
  applied green merge, ignored gray with tooltip. Do this before building
  speech-tail or particle-accretion code.
- Refactor the `ComposeAction` type to match `IntentKind` on the server:
  `interject | intercept | reroute | note | skip | retry | resume`. Today
  "Nudge" maps to `interject` and "Shape" maps to `reroute`, which is fine,
  but the frontend drops `skip`, `retry`, `resume`, and `note` even though the
  backend supports them. The Next-Step sheet should expose the subset listed
  in `intervention_options`.
- `MythosHeader`: compact line above the topbar pill, tappable to open a
  `PersonaMindSheet`. Derive from `GET /mythos` initially, upgrade to fold
  from `project_mythos_updated` events.

### 4.4 Narrator Agent

- Build in this order: deterministic digest -> narrator agent -> persona
  stance narrator. Do not start with the LLM.
- Run as an engine sidecar (post-phase hook), not as a workflow phase.
  Reasons:
  - workflow phases are operator-visible controls and the operator should not
    have to plan narration,
  - debounce/budget logic does not belong inside workflow config.
- Input packet is bounded by:
  - last 20 events or since-last-digest, whichever is smaller,
  - recent artifact excerpts capped at about 2 KB each, total <= 20 KB,
  - no full repo access.
- Output JSON is validated against the digest schema before ledger write.
  Invalid output emits `narrator_error`; no digest is emitted.
- Default provider: cheap/local. Operator opts into hosted narration per
  project.
- Per-run budget cap on narrator spend, surfaced in the existing cost HUD
  bucket.

### 4.5 Highest-Leverage Implementation Sequence

1. **Intent identity and outcomes.**
   Server-mint `client_intent_id`, persist queued intents, emit
   `operator_intent_applied` and `operator_intent_ignored` when
   `append_instruction` is consumed by a role. Frontend folds intents into
   `NarrativeSnapshot.pendingIntents`. Render a chip near the target atom with
   lifecycle color.

   Why first: closes the "does my nudge do anything" trust gap. Requires no
   LLM work. Unblocks everything else.

2. **Deterministic Next-Step Packet.**
   Backend `GET /next-step` plus emit `next_step_packet_created` at
   transitions. Frontend `NextStepSheet` plus `Next:` HUD chip. Compose dock
   moves into the sheet.

   Why second: the vision centers on next slated step, context preview, and
   drop-in. Deterministic first, LLM later.

3. **Mythos and persona events.**
   `synthesize_personas` emits `project_mythos_updated` and one
   `discussion_entry_created` per persona statement. Stance edits emit
   `persona_stance_updated`. Frontend Mythos header and Persona Mind Sheet.

   Why third: this is the founding team / persona minds half of the vision and
   is currently invisible.

4. **Event ledger cursor and SSE Last-Event-ID.**
   Pagination and reconnect correctness. Not glamorous, but everything above
   assumes durability and live/history parity.

5. **Deterministic DWAs.**
   Rule-based digest after `phase_done`, `gate_decided`, and `phase_error`.
   Render as a small satellite near the atom, with tap to story card citing
   events and artifacts.

   Why fifth: establishes the DWA UI shape and schema with zero LLM risk.

6. **Narrator agent using opencode `SessionRunner`.**
   Replaces or augments deterministic digest with richer synthesis. Enforce
   source-ref contract and cap budget.

7. **Flow / universe polish.**
   Pick one or two `spatial-flow-universe-design.md` slices: FlowPath
   foundation plus operator-intent packet visuals are highest value. Defer
   speech tails, actor animations, and loop cluster orbital solver until
   after items 1-6.

8. **Retire SRS section 9's screen list.**
   Rewrite the SRS so Mission Control, Replay, Memory, and Workflow are
   lenses, not tabs. Anyone building a new screen should justify why it is not
   a lens.

## 5. Straight Calls

- `pwa-narrative-replay-and-intervention-design.md` is the most valuable
  document in the set. It should be promoted above the flow-universe doc in
  the read order.
- `spatial-flow-universe-design.md` should be re-scoped. Declare most of it
  Phase 7+ or post-narrative-layer. Pare the near-term flow work down to:
  FlowPath refactor, operator-intent packet visuals, gate charge/release, and
  cost dust. Everything else is decoration relative to the stated vision.
- SRS section 9 contradicts `DIRECTION_GUARDRAILS.md`. One of them is wrong.
  Fix the SRS.
- The compose dock in `GameShell` is 80% of Slice 1 already built. Finish it
  by pointing it at a real Next-Step Packet and rendering lifecycle for
  submitted intents. That is the smallest path to the biggest user-visible
  jump.
- Ship deterministic before LLM everywhere: Next-Step Packet, DWA digest, and
  Mythos. LLM narration is leverage on top of a trustworthy surface, not a
  substitute for one.

End of review.
