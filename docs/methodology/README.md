# How guildr got built

This directory is the receipts. It is not part of the runtime — it's the
phase-by-phase plans and end-of-phase handoffs that a Qwen3 model, driven by
a one-screen bash harness, used to write everything in this repo.

If you want to see what the harness was actually told to do at each step,
read in this order:

1. **[plans/00-overview.md](plans/00-overview.md)** — top-level intent and the
   seven-phase split (foundation → ingestion → architect → roles →
   orchestrator → web → polish).
2. **[plans/01-conventions.md](plans/01-conventions.md)** — coding standards
   the model was expected to follow on every task.
3. **[plans/reference/](plans/reference/)** — context-window budget, the
   upstream llama.cpp contract, security model, error-handling rules,
   git-policy. These were embedded in every phase prompt as ground truth.
4. **[plans/phases/](plans/phases/)** — one document per phase, listing the
   tasks the harness fed to the model along with verifier commands and
   acceptance criteria.
5. **[handoff/](handoff/)** — what the model wrote back at the end of each
   phase: what got done, what was deferred, and what the next phase needs to
   know. These were appended to the prompt for the *following* phase so each
   model instance had context without re-reading the entire prior session.

The "dogfooding" claim in the top-level README isn't a metaphor — these are
the actual artifacts that drove the build. The retry-coach behaviour
described in the README was itself proposed during one of the phase-6
retries when the harness's initial verifier kept failing for reasons the
primary model couldn't diagnose on its own.

## What's missing from this archive

The bash harness itself (`bootstrap/build-phase.sh`, `bootstrap/lib/*.sh`)
lives in a separate repository and is not yet open-sourced. If there's
interest, file an issue and I'll get it cleaned up and pushed.
