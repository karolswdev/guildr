# Phase 7: Polish & Hardening

Everything not strictly required to ship v1 but needed to make the
system trustworthy and pleasant to use.

## Dependencies

- Phases 1-6 complete.

## Scope

- Structured logging with phase/role context.
- `/metrics` surface in PWA (already exposed in Phase 6; here we
  render it).
- Dry-run mode for testing the pipeline without burning tokens.
- Session inspection tooling.
- Documentation & example projects.
- Optional: raise `-np` or add orchestrator-side parallel-task queue.

## Tasks

### Task 1: Structured logging
- **Priority**: P1
- **Files**: `orchestrator/lib/logger.py`, update all roles to use it

**Acceptance Criteria:**
- [ ] JSON log format with standard fields: `ts`, `level`, `phase`,
      `task_id`, `session_id`, `event`, `message`
- [ ] Log level configurable via `config.logging.level`
- [ ] Per-phase log file at `.orchestrator/logs/<phase>.jsonl`
- [ ] LLM call logs include `prompt_tokens`, `completion_tokens`,
      `reasoning_tokens`, latency_ms

**Evidence Required:**
- `pytest tests/test_logger.py -v`
- Sample run: inspect `.orchestrator/logs/architect.jsonl` for
  expected fields

### Task 2: Metrics gauges in PWA
- **Priority**: P2
- **Dependencies**: Phase 6 Task 6
- **Files**: `web/frontend/src/components/Metrics.ts`

**Acceptance Criteria:**
- [ ] Polls `/api/llama/metrics` every 2s
- [ ] Renders tokens/sec (gen), prompt-eval tok/s, queue depth,
      VRAM-used / VRAM-total
- [ ] Sparkline of last 60s for each gauge
- [ ] Graceful degradation if upstream metrics endpoint missing

**Evidence Required:**
- Lighthouse: no UI-thread blocking
- Manual: confirm gauges track real activity during a run

### Task 3: Dry-run mode
- **Priority**: P1
- **Files**: `orchestrator/engine.py`,
  `orchestrator/lib/llm_fake.py`, tests

**Acceptance Criteria:**
- [ ] `--dry-run` flag swaps `LLMClient` for a fixture-driven fake
- [ ] Fake returns canned responses keyed by role+phase
- [ ] End-to-end dry-run produces all expected output files
- [ ] CI runs dry-run as part of test suite

**Evidence Required:**
- `pytest tests/test_dry_run.py -v`
- CI log: full pipeline under dry-run, zero real LLM calls

### Task 4: Session inspection CLI
- **Priority**: P2
- **Files**: `orchestrator/cli/inspect.py`

**Acceptance Criteria:**
- [ ] `orchestrator inspect <project-id>` lists phases + status
- [ ] `orchestrator inspect <project-id> --phase architect
      --attempt 2` dumps that session's transcript
- [ ] `orchestrator inspect <project-id> --tokens` shows per-phase
      token usage

**Evidence Required:**
- Manual: run inspect commands against a completed project dir

### Task 5: Documentation
- **Priority**: P1
- **Files**: `README.md`, `docs/getting-started.md`,
  `docs/architecture.md`, `docs/examples/todo-app/`

**Acceptance Criteria:**
- [ ] README has install, quickstart, screenshot of PWA
- [ ] Getting-started walks through a new project end-to-end
- [ ] Architecture doc summarises what's split across the plan files
- [ ] Example: a completed FizzBuzz project dir as fixture

**Evidence Required:**
- Fresh user (or a dry-run agent) follows getting-started and succeeds
- `markdownlint docs/ README.md` passes

### Task 6 (optional): Parallel coder tasks
- **Priority**: P3 (defer unless sprint is large)
- **Files**: `orchestrator/lib/queue.py` (extend)

**Acceptance Criteria:**
- [ ] Independent tasks (no shared dependencies) run in parallel
- [ ] Either raises `-np` on llama-server (requires restart) OR keeps
      `-np 1` and only parallelizes tool calls
- [ ] No deadlocks; queue tests still pass

**Evidence Required:**
- `pytest tests/test_queue_parallel.py -v`
- Timing test: 3 independent tasks complete in < 1.5× single-task
  time

## Phase exit criteria

- All P0/P1 tasks complete (Task 6 optional).
- Documentation sufficient for a new contributor (or a new opencode
  agent) to pick up.
- Dry-run passes in CI on every commit.
