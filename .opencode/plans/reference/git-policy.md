# Git Policy

Git is the orchestrator's source of truth for "a task is done". No
commit → task is not done, regardless of what the Evidence Log says.

## Why commits are mandatory

- Progress is cheap to lose without commits. Long runs get interrupted.
- The commit SHA is the only tamper-evident record that Coder's output
  and Tester's re-run agreed at a specific moment.
- Rollback on a failing downstream phase is `git reset --hard <sha>`;
  trivial when every task is a commit, painful otherwise.

## Repo lifecycle

- **On project create**: orchestrator runs `git init` in the project
  dir if it's not already a repo. `.gitignore` seeded with
  `.orchestrator/` (state, drafts, logs — not source of truth) and
  language-appropriate defaults.
- **Initial commit**: `qwendea.md` + `sprint-plan.md` (after Architect
  passes self-eval and human gate) committed together on branch `main`
  with message `phase-architect: initial sprint plan`.

## Per-task commits

One commit per task, made by the orchestrator (not the role) after:

1. Coder wrote source files.
2. Tester re-ran Evidence Required and returned `VERIFIED`.
3. All Evidence Log checkboxes in the task are ticked.

Commit message:

```
phase-<N>(task-<M>): <task name>

Verified-by: tester at <prior HEAD sha>
Evidence-log: sprint-plan.md#task-<M>
```

The orchestrator amends the task's Evidence Log with the commit SHA
**after** the commit lands:

```markdown
- [x] Committed as a1b2c3d
```

## Pre-task clean-state check

Before handing a task to Coder, orchestrator runs:

```bash
git diff-index --quiet HEAD --
```

Non-zero exit → "Unclean working tree" hard-fail (see
`error-handling.md`). The orchestrator never auto-stashes or
auto-discards — unexpected state means human investigation.

## Phase boundaries

On phase exit criteria satisfied, orchestrator tags:

```
phase-<N>-done
```

Annotated tag with the phase summary as the message. These are the
rollback anchors if a later phase discovers an earlier one was broken.

## Rollback

Rolling back a task:

```bash
git reset --hard <prior-task-sha>
```

Rolling back a whole phase:

```bash
git reset --hard phase-<N-1>-done
```

Orchestrator exposes this via `orchestrator rollback --task N` /
`--phase N`. Never force-push — this is a local repo; no upstream.

## What NOT to commit

- `.orchestrator/` (runtime state, drafts, event logs, escalations).
- Secrets, `.env`, credentials. Deployer role lists required env vars
  without touching values.
- Generated artifacts that aren't part of the product (coverage
  reports, etc.) — put them in `.orchestrator/` or `.gitignore` them.

## Signing

Out of scope for v1. If the user has a global `commit.gpgsign`, respect
it; don't override. Never pass `--no-gpg-sign`.
