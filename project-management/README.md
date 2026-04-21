# Council Zero-G PWA Project Plan

This directory is the execution hub for turning the orchestration platform into
a usable zero-g spatial PWA.

Use it when onboarding an agent, checking current status, choosing the next
task, or verifying that a phase is complete.

## Product Target

The PWA should make the LLM orchestration engine understandable and controllable
as a living spatial system:

- engine phases are objects and actors in a zero-g universe,
- loops are gravitational clusters, not dashboards or hex grids,
- flows show work, memory, cost, review, repair, replay, and human force,
- generated artifacts are visible as accreting objects and content previews,
- agent utterances are readable as directional speech tails,
- mobile Safari is a first-class control surface.

## Required Context

Read these before starting any phase:

- `project-management/STATUS.md`
- `project-management/AGENT_ONBOARDING.md`
- `project-management/DIRECTION_GUARDRAILS.md`
- `docs/AGENT_IN_PROGRESS_MEMORY_DUMP.md`
- `docs/spatial-flow-universe-design.md`
- `assets/poly-pizza/ultimate-space-kit/README.md`
- `assets/poly-pizza/ultimate-space-kit/manifest.json`

Read phase-specific files only when a phase requests them.

## Phase Order

| Phase | File | Goal | Status |
| --- | --- | --- | --- |
| 0 | `phases/00-baseline-and-invariants.md` | Preserve current working baseline and define evidence gates | Ready |
| 1 | `phases/01-flow-foundation.md` | Make paths/particles event-driven and testable | Ready |
| 2 | `phases/02-orbital-loop-layout.md` | Replace soft labels with logical orbital loop clusters | Ready |
| 3 | `phases/03-model-catalog-and-actors.md` | Wire Ultimate Space Kit as semantic model vocabulary | Ready |
| 4 | `phases/04-content-previews-speech-artifacts.md` | Show generated content, speech, and artifact lifecycle in-world | Ready |
| 5 | `phases/05-operator-touch-control.md` | Make Shape/Nudge/Intercept spatial and mobile-native | Ready |
| 6 | `phases/06-engine-consumption-and-run-control.md` | Make operator intents affect live orchestration runs | Ready |
| 7 | `phases/07-mobile-performance-and-polish.md` | Make the experience usable on mobile Safari | Ready |
| 8 | `phases/08-release-hardening.md` | Package, test, document, and stabilize for real users | Ready |

## Working Rules

- Pick the earliest phase with unfinished blocking tasks.
- Update `project-management/STATUS.md` before and after meaningful work.
- Keep phase edits scoped to the files listed in the task packet unless there
  is a concrete reason to expand scope.
- Do not preload heavy GLBs or the full Ultimate Space Kit.
- Keep all runtime assets local and vendored.
- Preserve the event-ledger invariant: replay folds durable events.
- Baseline device is iPhone portrait.

## Definition Of Usable

The system is usable when a non-developer can open the PWA on mobile and answer:

- What is active?
- What is blocked?
- What is being created?
- Who is speaking to whom?
- Which loop is progressing, repairing, reviewing, or shipping?
- Where is memory entering the run?
- Which path is expensive?
- What did my intervention change?

If the answer requires reading a table first, the spatial system is not done.
