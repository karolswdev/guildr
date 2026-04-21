# SDLC Loop Visualization

## Purpose

The PWA must make software delivery loops physically visible. A run is not only
a list of phases; it is a set of atomic SDLC loops consuming work, producing
artifacts, failing, retrying, getting reviewed, and feeding memory.

The operator should be able to look at the map and understand which pieces of
the software lifecycle are being eaten through the timeline right now.

## Loop Model

Each atom may participate in one or more SDLC loops:

- Discover: quiz, PRD gathering, persona forum, source reading.
- Plan: architect decomposition, micro-task breakdown, sprint planning.
- Build: implementation, file edits, tool calls.
- Verify: tests, lint, type checks, reviewer passes.
- Repair: failure interpretation, retry, guru escalation, remediation plan.
- Review: human gate, agent review, artifact inspection.
- Ship: deploy, release notes, post-run summary.
- Learn: MemPalace sync, wake-up update, replay template extraction.

The loop is an explicit state machine, not a visual afterthought.

```text
discover -> plan -> build -> verify -> review -> ship -> learn
                    ^         |
                    |         v
                    +------ repair
```

## Event Model

The event ledger must support loop events:

- `loop_entered`
- `loop_progressed`
- `loop_blocked`
- `loop_repaired`
- `loop_completed`
- `loop_reopened`

Required fields:

- `event_id`
- `schema_version`
- `run_id`
- `step`
- `atom_id`
- `loop_id`
- `loop_stage`
- `artifact_refs`
- `evidence_refs`
- `memory_refs`
- `cost_snapshot_ref` when relevant

Loop state must be derived by folding events. The Three.js scene must not store
loop state as graphics-only mutable history.

## Visual Grammar

Loops render as orbiting bands around atoms:

- Discover: thin cyan arc.
- Plan: blue arc.
- Build: white arc.
- Verify: green arc.
- Repair: amber-to-red arc.
- Review: purple arc.
- Ship: teal arc.
- Learn: lavender arc connected to MemPalace.

An atom can show multiple loop bands, but only the active loop animates. Idle
bands remain thin and low-contrast. A failed verify loop that enters repair
shows the repair arc physically pulling the atom backward along the timeline.

## Timeline Behavior

The replay timeline has lanes:

- Events lane.
- Cost density lane.
- SDLC loop lane.
- Artifact lane.
- Memory lane.

When scrubbing replay, loop arcs animate according to the selected event index.
The operator can filter to a loop stage and watch only build, verify, repair,
or learn passes.

## Atom Detail

The FocusPanel must show:

- Current loop stage.
- Previous loop stage.
- Next expected loop stage.
- Evidence required to advance.
- Artifact emitted by the current stage.
- Whether the atom has been reopened.
- Number of repair cycles.

## Acceptance Criteria

- Every atom can expose its current SDLC loop stage.
- Replay can show loop stage transitions without live state.
- Failed verification visibly enters repair.
- Guru escalation appears as a repair sub-loop, not as a disconnected event.
- MemPalace sync appears as the learn loop.
- The PWA can filter by loop stage.
- Loop visualization remains readable on iPhone portrait.
