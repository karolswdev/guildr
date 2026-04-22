# SRS Mini-Phase Pack

This directory decomposes `docs/srs-council-engine.md` + `docs/pwa-narrative-replay-and-intervention-design.md` into bite-sized, loadable phase files for executing agents.

Each file is designed so a fresh-context agent can load **that phase + the files it names** and ship a coherent slice without re-reading the entire SRS. Treat each mini-phase as a running checklist: check boxes as you complete them, append evidence, handoff cleanly.

## How to use

1. Read `../AGENT_ONBOARDING.md`, `../DIRECTION_GUARDRAILS.md`, `../STATUS.md` first. These never go stale.
2. Read `EXECUTION_CHECKLIST.md` — non-negotiable pre/during/post rules.
3. Read `QUALITY_GATES.md` — cross-phase invariants you must not violate.
4. Read `TRACEABILITY.md` if you need to map a SRS section or a design doc line back to a mini-phase.
5. Pick the earliest mini-phase whose `Done means` checkbox is still open and whose dependencies are satisfied.
6. Read only that phase file + the "Required context files" it lists.
7. Update checkboxes inline as you work. Do not delete a task; unchecking after flipping it checked is a signal of regression.
8. Append an Evidence Log row to `../STATUS.md` when a phase is complete.

## Ordering and dependency graph

Mini-phases are numbered by intended execution order, but the real dependency graph is a DAG. Edges mean "must be honestly done before the other can ship." A mini-phase may be **started** earlier for scaffolding if guarded by `fake_llm` / dry-run paths.

```
M1 event-ledger-foundation
   │
   ├── M2 intent-lifecycle-and-next-step
   │       │
   │       └── M6 pwa-lenses-and-map-surface
   │
   ├── M3 project-mythos-and-founding-team
   │       │
   │       └── M4 narrative-digest-and-discussion-log
   │               │
   │               └── M5 narrator-scribe-agent
   │
   ├── M7 artifact-previews-and-source-refs
   ├── M8 memory-spine-and-mempalace
   ├── M9 cost-budget-and-provider-telemetry
   ├── M10 hookability-and-workflow-control
   └── M11 live-run-and-replay-resilience
              │
              └── M12 release-hardening-and-quality-review
```

M1 is a hard prerequisite for M2–M6 because every narrative, intent, and lens surface folds events. M8 can run in parallel with M2/M3 because MemPalace already exists (see `STATUS.md`). M12 is the release gate; no mini-phase is "done" until M12's cross-phase checks pass.

## First delivery sequence

Start with slices that create leverage for every later phase:

1. **M08a Memory Provenance Packet** — make the existing MemPalace wake-up path observable: stable wake-up hash, `memory_refreshed` / `memory_status` events, loop memory refs, and next-step/DWA memory provenance.
2. **M02a Intent Lifecycle Kernel** — queue/apply/ignore operator interventions against the next-step packet.
3. **M04a Deterministic Discussion Log** — fold events into sourced narrative entries without an LLM narrator.
4. **M06a Tactical Map Memory Lens** — surface memory provenance and intervention points in the PWA without dashboard relapse.
5. **M08b MemPalace MCP For Opencode** — after deterministic memory provenance is green, expose MemPalace MCP to selected tool-enabled opencode agents as an optional live lookup channel.

## Non-negotiable invariants

These override any task-level decision. If a task conflicts with one of these, the task is wrong, not the invariant.

- **No dashboard relapse.** Never introduce a tab/table/card grid as primary surface. The PWA is a zero-g tactical map. See `../DIRECTION_GUARDRAILS.md`.
- **Events are the source of truth.** Folded frontend state must be reproducible from durable events. No hidden mutable state.
- **Every event carries `event_id`, `schema_version`, `ts`, `type`, `run_id`.** Readers MUST refuse unknown schema versions rather than silently mis-parse.
- **Source refs are mandatory on synthesis.** A narrator claim without event_id/artifact_ref is a bug.
- **Memory provenance is mandatory.** Opencode roles receive memory through deterministic wake-up injection first; MCP/live search can only augment that path.
- **Budget state is explicit.** `remaining_run_budget_usd` / `remaining_phase_budget_usd` are `null` when unset, never omitted.
- **Secrets are scrubbed at the boundary.** Use the existing `orchestrator/lib/scrub.py` — do not re-invent.
- **Mobile portrait is baseline.** If it overlaps on an iPhone, it is broken.
- **One `call_id` per LLM/advisor/session call site.** Threaded into raw-io, usage, pool, session-audit.
- **No filesystem time-travel in replay.** Replay is semantic reconstruction, not directory rollback.
- **Batteries provided, boundaries programmable.** Local defaults must work; every provider/hook/workflow boundary must remain configurable.

## How executing agents update checklists

- Open the mini-phase file in an editor.
- Flip `- [ ]` → `- [x]` when a task is **evidenced**, not just "looks right in code review."
- If a gate fails after you ticked it, revert the tick and add a one-line note: `-- regressed YYYY-MM-DD: <reason>`.
- When the whole phase is done, add a line at the bottom: `Completed YYYY-MM-DD by <agent>. Evidence: <rows in STATUS.md>`.
- Do not delete tasks or gates. Append `Deferred:` with a reason if scope changed.

## File map

- `README.md` — this file
- `EXECUTION_CHECKLIST.md` — pre/during/post rules every agent follows
- `QUALITY_GATES.md` — cross-phase invariants and review gates
- `TRACEABILITY.md` — SRS ↔ mini-phase mapping
- `M01-event-ledger-foundation.md`
- `M02-intent-lifecycle-and-next-step.md`
- `M03-project-mythos-and-founding-team.md`
- `M04-narrative-digest-and-discussion-log.md`
- `M05-narrator-scribe-agent.md`
- `M06-pwa-lenses-and-map-surface.md`
- `M07-artifact-previews-and-source-refs.md`
- `M08-memory-spine-and-mempalace.md`
- `M09-cost-budget-and-provider-telemetry.md`
- `M10-hookability-and-workflow-control.md`
- `M11-live-run-and-replay-resilience.md`
- `M12-release-hardening-and-quality-review.md`
