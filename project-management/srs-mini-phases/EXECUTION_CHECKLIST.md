# Execution Checklist

Every mini-phase run must pass through these three stages. Do not skip. This is the difference between "a passing test" and "a phase that actually shipped."

## Before starting a phase

- [ ] Read `../STATUS.md` — confirm no one else is mid-flight on this phase.
- [ ] Read the mini-phase file top-to-bottom. Load every file listed in "Required context files" before coding.
- [ ] Confirm the dependency graph in `README.md` is satisfied (upstream phases' `Done means` boxes are checked).
- [ ] Re-read `../DIRECTION_GUARDRAILS.md` if the phase touches the PWA.
- [ ] Re-read `QUALITY_GATES.md`. Print the cross-phase invariants that apply to this phase.
- [ ] State in your opening message: phase id, what you will change, what you will NOT change.
- [ ] If the phase requires a live endpoint/device, confirm availability before starting; otherwise declare a dry-run scope.

## During the phase

- [ ] Work the tasks in order unless there is a hard reason to reorder.
- [ ] Flip `- [ ]` → `- [x]` only when there is a reproducible evidence command or a committed artifact.
- [ ] Thread a single `call_id` per LLM/session call site (invariant).
- [ ] Never hardcode `require_human_approval`; honor the per-run opt-in (H1.3).
- [ ] Do not create a second source-of-truth for gates, call ids, mythos, digests, or intents.
- [ ] If the phase touches memory/opencode, preserve deterministic wake-up injection as the primary memory path; MCP/live search may only augment it.
- [ ] For every new event type, document `event_id`, `schema_version`, `ts`, `type`, `run_id` + payload shape inline in the mini-phase.
- [ ] Any new artifact path under `.orchestrator/` must be listed in the phase's "Implementation surface" section.
- [ ] If you discover a new trap, add it to the phase's `Known traps` section and to `../AGENT_ONBOARDING.md` if it is cross-phase.

## Before marking the phase done

- [ ] Every task checkbox checked or explicitly `Deferred:` with a reason.
- [ ] Every quality gate checkbox checked.
- [ ] Run the narrowest test command that covers your surface. Paste counts into STATUS.md.
- [ ] Run `git diff --check`. Must be clean.
- [ ] Walk through the applicable cross-phase gates in `QUALITY_GATES.md`.
- [ ] Add one Evidence Log row to `../STATUS.md` with exact commands and pass counts.
- [ ] Update the mini-phase file's footer: `Completed YYYY-MM-DD by <agent>`.
- [ ] If a new primitive, artifact path, or event type was introduced: update the phase's `Handoff notes` and add a glossary entry in `../AGENT_ONBOARDING.md`.
- [ ] Do not commit without user approval. Write the proposed commit message into the handoff notes instead.

## Refusal criteria

Stop and escalate rather than "force it through" if any of the following are true:

- A cross-phase quality gate would regress.
- An invariant from `README.md` would be violated.
- A new shadow registry, second call_id source, or dashboard tab would be introduced.
- Tests would need to be relaxed to pass.
- The UI would require scrolling a table to answer one of the `DIRECTION_GUARDRAILS.md` quality questions.

## Signals that you are off-track

- You are adding a new configuration file that duplicates `config.yaml`'s `endpoints:` / `routing:` block.
- You are composing a prompt by concatenating whole-repo file contents.
- You are emitting an event without `event_id` or `schema_version`.
- You are writing a narrative claim without a source ref.
- You are letting an opencode role rely on session continuity or MCP availability for mandatory project memory.
- You are adding a gate default of `True` / `False` anywhere hardcoded.
- You are precaching anything from `assets/poly-pizza/ultimate-space-kit/` in the service worker.

If any of these is happening: back up, re-read the relevant mini-phase, and ask the operator.
