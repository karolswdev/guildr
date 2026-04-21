# Direction Guardrails

This file exists to keep implementation aligned with the product vision. A task
can pass tests and still be wrong if it violates these constraints.

## North Star

The map is a zero-g operational universe for the LLM orchestration engine.
Users should understand and influence the run by looking at objects, flows,
motion, content previews, and actor behavior.

## Do This

- Use the engine state machine as the visual source of truth.
- Make loops read as gravitational systems of related bodies.
- Make generated work visible as artifacts and surface previews.
- Make agent communication directional with speech tails.
- Use Ultimate Space Kit models semantically:
  - astronaut: operator, reviewer, human presence,
  - mech: implementation/build worker,
  - rover: tests, tools, CI, local commands,
  - spaceship: deploy, transfer, handoff,
  - planets: loop bodies and cluster anchors,
  - connectors/pickups: dependencies, gates, artifacts, status tokens,
  - radar/antenna/solar: memory, providers, telemetry, budget/energy.
- Keep mobile touch control primary.
- Use motion and spatial grouping before labels.
- Load models progressively and intentionally.

## Do Not Do This

- Do not return to a hex board, lattice floor, or dashboard-first UI.
- Do not scatter models as random decoration.
- Do not make every event a rectangular card.
- Do not load all 87 Ultimate Space Kit models on first render.
- Do not make the user read a table to know what is active or blocked.
- Do not add landing-page or marketing composition to the map route.
- Do not let text overlap or become unreadable on mobile.

## Quality Questions

Every feature should answer at least one of these:

- What is active right now?
- What is blocked and why?
- What is being created?
- Who created it?
- Where is it going next?
- Who is speaking to whom?
- Is the loop progressing, repairing, reviewing, or shipping?
- Where is memory entering the run?
- Which path is expensive?
- What did the operator change?

## Review Gate For Visual Work

Before marking a visual task done, capture or inspect:

- mobile portrait,
- desktop/wide viewport,
- selected atom,
- active flow,
- blocked or repair state,
- at least one deferred model loaded,
- no-overlap state for HUD/labels/previews.

The reviewer should reject work that is merely decorative. Every visible object
needs either semantic meaning, orientation value, or interaction value.
