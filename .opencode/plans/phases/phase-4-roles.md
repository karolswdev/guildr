# Phase 4: Coder, Tester, Reviewer, Deployer

The non-Architect roles. All share the "same Qwen, different system
prompt" pattern. Each role is ~100-200 LOC.

## Dependencies

- Phase 1: `LLMClient`, `State`
- Phase 3: `sprint-plan.md` exists and has passed Architect self-eval

## Shared patterns

### `orchestrator/roles/base.py`

```python
class BaseRole:
    def __init__(self, llm: LLMClient, state: State, config: Config):
        self.llm = llm
        self.state = state
        self.config = config

    def _chat(self, system: str, user: str, **kw) -> LLMResponse:
        return self.llm.chat(
            [{"role": "system", "content": system},
             {"role": "user",   "content": user}],
            **kw,
        )

    def _load_prompt(self, name: str) -> str:
        """Load a prompt template from roles/prompts/<role>/<name>.txt."""
        ...
```

### Context-slicing helpers

All roles use helpers from `orchestrator/lib/sprint_plan.py`:

```python
def parse_tasks(sprint_plan_md: str) -> list[Task]: ...
def slice_task(sprint_plan_md: str, task_id: int) -> str: ...
    # Returns: the task's section + the "## Architecture Decisions"
    # header, only.
def apply_evidence_patch(sprint_plan_md: str, patch: dict) -> str: ...
    # Deterministic update — no LLM involved. Ticks checkboxes and
    # appends evidence outputs.
```

See `reference/context-budget.md` for why slicing matters.

## 4.1 Coder

**Input**: `sprint-plan.md` (sliced to one task at a time)
**Output**: Source files + filled Evidence Log patch

### Workflow

1. Parse tasks from `sprint-plan.md`.
2. For each task in dependency order:
   1. Slice the task section.
   2. Call LLM with coder prompt: implement + emit Evidence Log patch.
   3. Parse the patch JSON (same JSON-robustness pattern as Architect).
   4. Apply patch to `sprint-plan.md` deterministically.
3. Return when all tasks processed.

### Coder prompt shape

```text
You are an experienced software engineer. Implement the following task
according to the sprint plan. Follow the Architecture Decisions below.

ARCHITECTURE DECISIONS:
<architecture section>

TASK:
<sliced task>

AFTER implementing:
1. Run the commands from "Evidence Required" and capture output.
2. Emit a JSON patch (ONLY, no prose) with this schema:

{
  "task_id": <N>,
  "entries": [
    {"check": "<what was checked>", "output": "<actual output>", "passed": <bool>},
    ...
  ]
}

Note: `commit_sha` is NOT set by Coder. The orchestrator commits after
Tester returns VERIFIED and amends the Evidence Log with the SHA.

If a step failed, set passed=false and put the failure in `output`. Do
NOT mark something passed that you could not verify.
```

## 4.2 Tester

**Input**: `sprint-plan.md` (tasks with filled Evidence Logs)
**Output**: `TEST_REPORT.md`

The Tester's purpose is **independent re-verification** — the Coder
self-reported, so the Tester re-runs the Evidence Required commands
and compares.

### Workflow

1. Parse tasks from `sprint-plan.md`.
2. For each task with a filled Evidence Log:
   1. Re-run Evidence Required commands (via bash tool — Qwen in
      opencode has shell access).
   2. Compare observed output to Evidence Log's recorded output.
   3. Mark task `verified`, `mismatch`, or `re-run-failed`.
3. Write `TEST_REPORT.md` with per-task status and any mismatches.
4. On `VERIFIED`: signal orchestrator to commit the task. Orchestrator
   runs `git add -A && git commit -m "phase-<N>(task-<M>): ..."` per
   `reference/git-policy.md`, then patches the Evidence Log with
   `- [x] Committed as <short-sha>`. On `MISMATCH`/`RERUN_FAILED`: no
   commit; phase validator fails and retries with failure context.

### Tester prompt shape

```text
You are a QA engineer. The Coder claims the following task is done and
has filled the Evidence Log. Your job is to RE-RUN each Evidence
Required step and confirm. You are allowed to run shell commands.

TASK:
<sliced task>

CODER'S EVIDENCE LOG:
<filled evidence log>

For each evidence item, re-run the command and report PASS/FAIL. Be
strict — if the Coder's recorded output doesn't match what you see,
mark as MISMATCH with both outputs.

Output markdown:

### Task <N>: <Name>
- Status: VERIFIED | MISMATCH | RERUN_FAILED
- Evidence 1: <PASS|FAIL> — <your output>
- Evidence 2: ...
- Notes: ...
```

## 4.3 Reviewer

**Input**: `sprint-plan.md`, codebase, `TEST_REPORT.md`
**Output**: `REVIEW.md`

The Reviewer does a code-review-grade pass: correctness, security,
architecture compliance. **Does not re-run tests** — that's Tester's
job.

### Workflow

1. Load sprint-plan (acceptance criteria only, not full Evidence
   sections — save tokens).
2. Load `TEST_REPORT.md`.
3. Generate a `git diff` summary (not full diffs — headline per file).
4. Call LLM with reviewer prompt.
5. Parse per-criterion PASS/FAIL output into `REVIEW.md`.

### Reviewer prompt shape

```text
You are a senior code reviewer. Review the implementation against the
sprint plan. Do NOT re-run tests (that was the Tester's job) — focus
on code quality, security, architecture compliance.

SPRINT PLAN (acceptance criteria):
<criteria only>

TEST REPORT:
<test report>

GIT DIFF SUMMARY:
<diff summary>

For each acceptance criterion, output:
- [PASS|FAIL|CONCERN] Criterion: <text>
  - Notes: <what you observed>

Then a "## Overall" section with one of:
- APPROVED
- APPROVED WITH NOTES
- CHANGES REQUESTED (with list of required changes)
- CRITICAL (security or correctness issue found)
```

## 4.4 Deployer

**Input**: code + `REVIEW.md`
**Output**: `DEPLOY.md` + deployment scripts

Minimal role — most projects don't deploy on day one. Deployer:

1. Detects existing deployment config (Dockerfile, docker-compose,
   railway/fly/etc. config).
2. Lists required environment variables (grep for `os.environ` or
   equivalent).
3. Produces `DEPLOY.md` with: deployment target, required env, manual
   steps, smoke-test commands.

**Never pastes secrets into prompts.** See `reference/security.md`.

## Tasks

### Task 1: Shared helpers
- **Priority**: P0
- **Files**: `orchestrator/roles/base.py`,
  `orchestrator/lib/sprint_plan.py`, `tests/test_sprint_plan.py`

**Acceptance Criteria:**
- [ ] `parse_tasks` returns tasks in order with id, name, deps, body
- [ ] `slice_task` returns the correct section + architecture header
- [ ] `apply_evidence_patch` ticks checkboxes and inserts outputs
      idempotently
- [ ] Round-trip: parse → slice → patch → parse unchanged task count

**Evidence Required:**
- `pytest tests/test_sprint_plan.py -v`
- Fixture: sample `sprint-plan.md` with 5 tasks

### Task 2: Coder role
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/roles/coder.py`, prompts,
  `tests/test_coder.py`

**Acceptance Criteria:**
- [ ] Processes tasks in dependency order
- [ ] Emits valid evidence patch JSON
- [ ] Handles JSON malformed output (same robustness pattern as
      Architect)
- [ ] Writes source files per task
- [ ] Applies evidence patch deterministically

**Evidence Required:**
- `pytest tests/test_coder.py -v`
- Integration on real server: given a 2-task sprint-plan fixture,
  produces working code and valid Evidence Logs

### Task 3: Tester role
- **Priority**: P0
- **Dependencies**: Task 2
- **Files**: `orchestrator/roles/tester.py`, prompts,
  `tests/test_tester.py`

**Acceptance Criteria:**
- [ ] Re-runs Evidence Required commands
- [ ] Produces `TEST_REPORT.md` with VERIFIED|MISMATCH|RERUN_FAILED per
      task
- [ ] Flags Coder-evidence/observed-output mismatches
- [ ] On any MISMATCH or RERUN_FAILED, phase validator fails

**Evidence Required:**
- `pytest tests/test_tester.py -v`
- Mismatch test: fixture where Coder's recorded output differs from
  observed → Tester detects and flags

### Task 4: Reviewer role
- **Priority**: P1
- **Dependencies**: Task 3
- **Files**: `orchestrator/roles/reviewer.py`, prompts,
  `tests/test_reviewer.py`

**Acceptance Criteria:**
- [ ] Produces `REVIEW.md` with per-criterion PASS/FAIL/CONCERN
- [ ] Ends with one of 4 overall verdicts
- [ ] CRITICAL verdict blocks pipeline
- [ ] Does NOT re-run tests

**Evidence Required:**
- `pytest tests/test_reviewer.py -v`
- Integration on real server with a sample implementation

### Task 5: Deployer role
- **Priority**: P2
- **Dependencies**: Task 4
- **Files**: `orchestrator/roles/deployer.py`, prompts,
  `tests/test_deployer.py`

**Acceptance Criteria:**
- [ ] Detects Dockerfile, docker-compose, etc.
- [ ] Lists required env vars without exfiltrating values
- [ ] Produces `DEPLOY.md`

**Evidence Required:**
- `pytest tests/test_deployer.py -v`

## Phase exit criteria

- All 5 tasks' Evidence Logs verified.
- End-to-end: given a passing Phase-3 sprint-plan, Coder → Tester →
  Reviewer produces code + TEST_REPORT + REVIEW with no CRITICAL.

## What's next

Phase 5 (`phase-5-orchestrator.md`) — wire everything together.
