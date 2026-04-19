# Conventions & File Formats

## Files per project

```
<project-dir>/
├── qwendea.md              # Source of truth — what we're building
├── sprint-plan.md          # Architect's plan with tasks + Evidence
├── TEST_REPORT.md          # Tester's output
├── REVIEW.md               # Reviewer's output
├── DEPLOY.md               # Deployer's output
├── .orchestrator/
│   ├── state.json          # Phase, retries, session IDs
│   ├── sessions/           # Exported session transcripts
│   └── logs/               # Structured logs per phase
└── <source tree>
```

## `qwendea.md` format

"**W**hat **W**e **N**eed to **D**o, **E**xactly, **A**nd." The Architect
reads this as a contract. Fixed structure:

```markdown
# Project: <Name>

## Description
2-3 sentence summary.

## Target Users
Who uses this, and the problem it solves.

## Core Requirements
1. <Requirement — specific and testable>
2. <Requirement — specific and testable>
3. ...

## Constraints
- Tech stack
- Performance
- Security
- Other

## Out of Scope
- Explicitly excluded items
```

## `sprint-plan.md` format

The Architect produces this. **Every task MUST have an Evidence Required
and Evidence Log section.** No exceptions.

```markdown
# Sprint Plan

## Overview
2-3 sentences covering the implementation strategy.

## Architecture Decisions
- Decision 1 (with rationale)
- Decision 2 (with rationale)

## Tasks

### Task 1: <Name>
- **Priority**: P0 | P1 | P2 | P3
- **Dependencies**: <task IDs or "none">
- **Files**: <files to create/modify>

**Acceptance Criteria:**
- [ ] Criterion 1 (verifiable)
- [ ] Criterion 2 (verifiable)

**Evidence Required:**
- Run `<exact test command>` and observe `<expected output>`
- `git diff` should show changes in `<path>`
- Manual verification: `<step>` (only if automation impossible)

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Git diff verified in <path>
- [ ] Manual verification passed
- [ ] Committed as <short-sha>  <!-- mandatory; filled after commit -->


**Implementation Notes:**
<Specific guidance, edge cases, gotchas>

### Task 2: ...

## Risks & Mitigations
1. <Risk> — <Mitigation>
2. <Risk> — <Mitigation>
3. <Risk> — <Mitigation>
```

## Acceptance-criteria language rules

Every criterion must be **verifiable without human judgment**.

| Bad (vague)       | Good (verifiable)                                                       |
|-------------------|-------------------------------------------------------------------------|
| "The API is fast" | "`curl /healthz` returns in < 50 ms (p95 over 100 requests)"            |
| "UI is responsive"| "At 375px width, nav collapses to a hamburger menu"                     |
| "Data is secure"  | "Passwords stored as argon2id hashes; plaintext never touches disk"     |
| "Works well"      | "`pytest tests/` passes with 0 failures and ≥80% coverage"              |

If a criterion doesn't map to a command or specific observable, rewrite it.

## Priority conventions

- **P0**: Blocks everything downstream. Do first.
- **P1**: Core feature. Must ship.
- **P2**: Important but deferrable.
- **P3**: Nice-to-have / polish.

Sprint-plans exceeding 3 P0 tasks should be flagged — the Architect's
`feasibility` self-eval criterion catches this.

## Task ID format

Section header regex: `^### Task (\d+): (.+)$`. Internal IDs: `task-<N>`.

## Evidence Log patch format (Coder → file)

The Coder does NOT round-trip the full `sprint-plan.md` to update a
checkbox. It emits a patch JSON that a deterministic Python applier
writes into the file:

```json
{
  "task_id": 3,
  "entries": [
    {"check": "Test command run", "output": "...", "passed": true},
    {"check": "Git diff in lib/state.py", "passed": true},
    {"check": "Manual verification passed", "passed": false}
  ]
}
```

See `reference/context-budget.md` for why.

## Git commit discipline (mandatory)

A task is only "done" when its work is committed. The Evidence Log's
last checkbox — `Committed as <sha>` — is not optional. See
`reference/git-policy.md` for the full policy; the essentials:

- **One commit per task**, made by the orchestrator after Tester
  returns `VERIFIED`. Never batch multiple tasks.
- **Commit message format** (enforced by bootstrap verifier):
  ```
  phase-<N>(task-<M>): <task name>

  Verified-by: tester at <prior HEAD sha>
  Evidence-log: sprint-plan.md#task-<M>
  ```
- **Pre-task clean-state check**: orchestrator runs
  `git diff-index --quiet HEAD --` before handing a task to Coder.
  Dirty tree → hard-fail (see `reference/error-handling.md`).
- **Phase boundary tags**: `phase-<N>-done` annotated tags are the
  rollback anchors.
- **`.orchestrator/` is gitignored**; runtime state is not source of
  truth.
