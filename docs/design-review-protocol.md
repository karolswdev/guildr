# Design Review Protocol

## Purpose

Council Engine design changes need structured review. A single assistant pass
or one external model pass is not enough for major architecture decisions.

This protocol defines how design docs are reviewed before implementation work
is assigned to low-context agents.

## Review Hats

Major design changes require at least these hats:

- Systems architect: event sourcing, replay, schema evolution, idempotency,
  crash recovery.
- FinOps/provider specialist: provider usage, local estimates, budgets,
  source/confidence labels, exports.
- Mobile PWA/game UX director: iOS feel, touch hierarchy, visual grammar,
  accessibility, delight without clutter.
- Local inference operator: llama.cpp, local model health, throughput, context
  pressure, hardware constraints.
- Security/operator safety: secrets, sandboxing, logs, permission boundaries,
  replay export hygiene.

## Invocation Rules

- Do not run multiple write-capable external reviewers in parallel against the
  same files.
- Prefer read-only review first. Apply patches manually or in a single
  controlled write pass.
- If an external reviewer is allowed to patch, give it a disjoint file scope.
- Every external review must state its hat, files inspected, findings, patches,
  and residual risks.
- Every claim about a fast-moving provider API must be checked against primary
  documentation before it is committed.
- All doc changes must pass ASCII and `git diff --check`.

## Best-In-Class Gate

Before implementation starts, a design packet must answer:

- What is the invariant?
- Where is it recorded durably?
- How does replay reconstruct it?
- How does the PWA show it live and in replay?
- What does the user do when it fails?
- What does a low-context agent need to execute it?
- What are the acceptance tests?

If any answer is missing, the design is not ready for implementation.

## Review Artifacts

Review results should be stored as durable docs or issue comments, not hidden in
chat. Recommended project-local artifacts:

- `docs/design-review-protocol.md`
- `docs/review-notes/*.md`
- `.orchestrator/reviews/*.jsonl`

The event ledger should eventually emit `design_review_completed` events when
reviews are run inside the framework itself.
