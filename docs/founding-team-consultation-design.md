# Founding Team Consultation Design

Last updated: 2026-04-22

## Purpose

Founding-team consultation makes personas recurring project voices without
turning the orchestrator into an unbounded debate loop. The team can warn,
clarify, narrow, defer, or request operator approval. It cannot silently expand
scope, rewrite the project goal, or invalidate prior accepted decisions.

This design closes the A-8 direction: personas are not only synthesized once at
project seed; they are consulted at load-bearing moments and projected into the
durable discussion log for the PWA.

## Product Rule

Treat each consultation as a bounded roundtable, not a free-form meeting.

- One consultation is tied to one trigger event.
- One concise statement is produced per persona.
- One convergence note summarizes the team position.
- Any scope expansion becomes `operator_decision_required`, not an automatic
  workflow mutation.
- All statements cite source refs: triggering event, artifacts, prior decision,
  gate, digest, or next-step packet.
- The operator may invite a temporary Hero reviewer into a consultation, but
  the Hero has a declared mission and term limit.

## Trigger Inputs

Each consultation receives a `FoundingTeamConsultation` packet:

```json
{
  "trigger_type": "phase_failed",
  "trigger_event_id": "evt_123",
  "current_step": "architect_refine",
  "project_goal": "Build an orchestration PWA",
  "personas": [],
  "prior_decisions": [],
  "project_memory": {
    "wake_up_hash": "sha256...",
    "memory_refs": [".orchestrator/memory/wake-up.md"],
    "wake_up_excerpt": "Bounded project memory excerpt..."
  },
  "persona_memory": [],
  "current_artifacts": [],
  "next_step_packet": {},
  "recent_discussion_refs": [],
  "invited_heroes": [],
  "allowed_motion": [
    "clarify",
    "narrow",
    "defer",
    "add_evidence",
    "operator_decision_required"
  ],
  "disallowed_motion": [
    "new_major_feature",
    "rewrite_project_goal",
    "expand_scope_without_operator_approval"
  ]
}
```

The packet should be small. Prefer artifact refs and short excerpts over full
files. Prior accepted decisions are binding context, not suggestions.

## Context Assembly

The consultation packet is assembled from five bounded layers, in this order:

1. **Identity layer**
   - project id and title,
   - current step,
   - trigger event id/type,
   - consultation id,
   - current next-step packet summary.

2. **Project memory layer**
   - `memory_provenance()` output from `.orchestrator/memory/wake-up.md`,
   - stable `wake_up_hash`,
   - `memory_refs`,
   - a bounded wake-up excerpt,
   - optional `last_search` excerpt only when the trigger explicitly requested
     a memory search.

3. **Persona memory layer**
   - current persona definition from `FOUNDING_TEAM.json`,
   - persona mandate,
   - perspective,
   - veto scope,
   - recent statements by that persona from `.orchestrator/discussion/log.jsonl`,
   - prior stance edits once `persona_stance_updated` exists.

4. **Decision layer**
   - prior accepted scope/convergence from `PERSONA_FORUM.md`,
   - approved gate decisions,
   - recent convergence highlights,
   - operator-approved scope changes only.

5. **Evidence layer**
   - trigger event payload,
   - relevant artifact refs and short excerpts,
   - latest narrative digest / discussion highlights,
   - current queued operator intents that target this consultation.

The packet must not include full raw logs, full artifact bodies, secrets, or
unbounded discussion history. Every included excerpt needs a source ref.

### What A Persona Sees

Each persona receives the same shared packet plus a persona-specific section:

```text
You are: Founder
Perspective: business owner
Mandate: Keep the project aligned with purpose and scope.
Veto scope: product misalignment

Your recent memory:
- event:disc_1 — You asked to preserve replayability over dashboard sprawl.
- event:disc_9 — You accepted the current A-8 bounded-consultation scope.

Current trigger:
- phase_failed on architect_refine
- source refs: event:evt_123, artifact:sprint-plan.md

Project memory:
- wake_up_hash: sha256...
- memory refs: .orchestrator/memory/wake-up.md
- excerpt: ...

Prior binding decisions:
- The PWA map is the primary surface.
- Consultations cannot silently expand scope.

Allowed response:
- one concise statement
- classify as clarify, narrow, defer, add_evidence, or operator_decision_required
- cite source refs
```

Deterministic v1 can construct this internally without calling a model. A
model-backed version should use this exact packet shape as the prompt body.

### What A Hero Sees

A Hero receives the shared packet plus the Hero invitation:

```text
Hero: Systems Critic
Mission: Look for hidden orchestration failure modes before the next gate.
Watch for: scope drift, missing replay evidence, unbounded agent loops.
Term: until_deliverable(A-8 consultation implementation)
Originating operator intent: intent_123
```

The Hero should not receive special authority. The Hero sees the same project
memory and prior decisions as the founding team, plus its own mission and term.
Hero output must cite the operator intent that invited it.

## Memory Injection Rules

Memory is injected through two channels:

1. **Deterministic prompt packet, mandatory.**
   The consultation packet includes `memory_provenance()`, `wake_up_hash`,
   `memory_refs`, and a bounded wake-up excerpt. This is the replayable memory
   contract and must exist for deterministic personas, model-backed personas,
   and Heroes.

2. **Live memory lookup, optional.**
   A model-backed Hero or persona may request a targeted MemPalace search only
   when the trigger or operator intent asks for it. Search results are cached,
   scrubbed, source-refed, and attached as `memory_search_refs`. They supplement
   the wake-up packet; they never replace it.

Persona memory is not a separate hidden chat transcript. It is rebuilt from
durable project state:

- `FOUNDING_TEAM.json`,
- `PERSONA_FORUM.md`,
- `discussion_entry_created` rows by that persona,
- `discussion_highlight_created` convergence rows,
- future `persona_stance_updated` events.

This keeps replay deterministic: a consultation at event 200 should use the
memory and persona history known at event 200, not the current filesystem state
after event 500.

## Output Contract

The first implementation should write deterministic discussion rows. A later
model-backed implementation may use the same schema.

```json
{
  "consultation_id": "founding_evt_123",
  "trigger_event_id": "evt_123",
  "entries": [
    {
      "speaker": "Founder",
      "entry_type": "postmortem:phase",
      "text": "The failure points to missing evidence, not a reason to expand scope.",
      "stance": "concern",
      "allowed_motion": "add_evidence",
      "source_refs": ["event:evt_123", "artifact:sprint-plan.md"],
      "decision_refs": ["decision:scope:v1"]
    }
  ],
  "convergence": {
    "text": "Keep scope unchanged; add evidence before retry.",
    "recommended_action": "add_evidence",
    "scope_delta": "none"
  }
}
```

Discussion rows should use existing `discussion_entry_created` and
`discussion_highlight_created` events. Add metadata fields rather than creating
a second discussion system.

## Hero Interjection

A Hero is an operator-invited powerful model or specialist lens that can join
the council for a bounded purpose. It is not a permanent founding-team persona
unless the operator later promotes it through an explicit persona update.

Hero invitation is an operator intent with a mission:

```json
{
  "kind": "invite_hero",
  "hero": {
    "name": "Systems Critic",
    "provider": "openrouter",
    "model": "anthropic/claude-opus",
    "mission": "Look for hidden orchestration failure modes before the next gate.",
    "watch_for": [
      "scope drift",
      "missing replay evidence",
      "unbounded agent loops"
    ],
    "term": {
      "mode": "until_deliverable",
      "deliverable": "A-8 consultation implementation"
    }
  },
  "target": {
    "consultation_trigger": "gate_opened",
    "step": "architect_refine"
  }
}
```

Supported terms:

- `single_consultation`: Hero joins one consultation only.
- `until_step_complete`: Hero joins consultations for one workflow step.
- `until_deliverable`: Hero remains available until a named deliverable lands.
- `manual_dismissal`: Hero stays active until the operator dismisses it.

Hero guardrails:

- Hero output is advisory discussion state unless separately consumed by a role
  prompt or approved operator intent.
- Hero mission and `watch_for` fields constrain the response.
- Hero cannot override founding-team convergence by itself.
- Hero cannot silently create new scope; scope expansion still becomes
  `operator_decision_required`.
- Hero rows must be tagged with `speaker_kind: "hero"` in metadata and include
  the originating `operator_intent_id`.
- Hero use should emit usage/cost telemetry like any other model-backed call.

PWA treatment:

- The Hero appears as a temporary high-signal body or beam entering the council.
- The consultation sheet labels the Hero's mission and term.
- The operator can dismiss, renew, or promote the Hero from the Hero detail
  affordance.
- Hero statements should visually stand apart from founding-team personas, so
  the operator can tell permanent project identity from temporary expert input.

## Prompt Contract For A Model-Backed Version

If a model is used, it should be one bounded call returning structured JSON for
all personas plus convergence. Do not run recursive persona-to-persona debate
in the first version.

System intent:

```text
You are producing a bounded founding-team consultation for an orchestration run.

You are given the project goal, founding-team personas, prior accepted
decisions, the triggering event, relevant artifact excerpts, recent discussion,
and the next planned step.

For each persona, write one concise advisory statement grounded in that
persona's mandate and veto scope. Do not reopen settled scope unless the
trigger reveals a direct contradiction, missing evidence, or execution risk.
Do not request major new features.

If a change is needed, classify it as one of:
- clarify
- narrow
- defer
- add_evidence
- operator_decision_required

Return JSON only matching the consultation schema.
```

## Trigger Mapping

| Trigger event | Entry type | Persona job | Scope rule |
| --- | --- | --- | --- |
| `project_seeded` | `persona_statement` | Establish founding team | May define initial scope |
| `architect_plan_drafted` | `review:plan` | Check plan against goal and prior decisions | No expansion; can narrow or request evidence |
| `architect_refine_done` | `review:refine` | Confirm refinement respected approved direction | No expansion |
| `micro_task_split` | `review:micro` | Check task boundaries and evidence | No expansion; can split smaller |
| `gate_opened` | `advisory:gate` | Give operator concise review context | No expansion |
| `gate_rejected` | `postmortem:gate` | Explain why rejection matters | No expansion; can request retry evidence |
| `phase_failed` | `postmortem:phase` | Diagnose failure against persona concerns | No expansion |
| `phase_retried` | `advisory:retry` | Nudge the retry toward the smallest correction | No expansion |

## PWA Presentation

The PWA should surface consultations as a Founding Team pulse:

- short persona rows around the Goal Core / Founding Team cluster,
- one convergence strip,
- source chips for trigger, artifact, and prior decision refs,
- clear badges: `scope unchanged`, `minor correction`, or
  `operator decision required`,
- temporary Hero badge when a Hero was invited into this consultation,
- speech tails from persona bodies to the decision or atom they reacted to.

The UI can feel like a dialogue surface, but the content is project counsel,
not roleplay.

## Guardrails

- Idempotency: one consultation per trigger event id.
- Boundedness: one row per persona plus one convergence highlight.
- Source credibility: every row has `source_refs`.
- Scope control: `scope_delta != "none"` requires explicit operator handling.
- No mutation: consultation writes discussion state only; it does not edit
  workflow, artifacts, or task scope directly.
- Hero containment: a Hero has a mission, term, source intent, and telemetry;
  it is never silently promoted into the founding team.
- Replayability: outputs are durable discussion events, so replay can show what
  the founding team knew and said at that time.

## First Implementation Slice

1. Add deterministic `PersonaForum.consult(...)`.
2. Load existing `FOUNDING_TEAM.json`; synthesize personas if missing only when
   the project explicitly runs persona synthesis.
3. Accept trigger event, current step, source refs, and optional artifact refs.
4. Emit `discussion_entry_created` per persona and one
   `discussion_highlight_created` convergence note.
5. Record consultation metadata:
   `consultation_id`, `trigger_event_id`, `allowed_motion`, `scope_delta`.
6. Accept queued `invite_hero` operator intents in the consultation packet but
   initially render them as deterministic placeholder/advisory rows unless a
   model-backed Hero runner is configured.
7. Wire only the safest first triggers:
   `phase_error`, `phase_retry`, and `gate_decided` rejection.
8. Add tests for idempotency, source refs, scope-delta guardrails, Hero term
   metadata, and PWA discussion fold visibility.
