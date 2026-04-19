# Phase 4 Handoff — Coder, Tester, Reviewer, Deployer

## What this phase actually built

**Non-Architect roles** — all share "same Qwen, different system prompt" pattern.

### Key files and modules

| File | Purpose |
|------|---------|
| `orchestrator/roles/base.py` | `BaseRole` — shared LLM chat, prompt loading, state access |
| `orchestrator/roles/coder.py` | `Coder` — implements tasks from sprint-plan.md in dependency order |
| `orchestrator/roles/tester.py` | `Tester` — independently re-verifies Coder's Evidence Log |
| `orchestrator/roles/reviewer.py` | `Reviewer` — code-review-grade pass against sprint plan |
| `orchestrator/roles/deployer.py` | `Deployer` — produces DEPLOY.md with deployment plan |
| `orchestrator/lib/sprint_plan.py` | `parse_tasks`, `slice_task`, `apply_evidence_patch` — shared helpers |

### Prompt templates

- `prompts/coder/generate.txt` — Coder prompt with architecture + task + JSON patch schema
- `prompts/tester/generate.txt` — Tester prompt with task + filled evidence log
- `prompts/reviewer/generate.txt` — Reviewer prompt with acceptance criteria + test report + git diff
- `prompts/deployer/generate.txt` — Deployer prompt with configs + env vars + review verdict

### Entry points

- `Coder.execute(sprint_plan_path)` → returns sprint_plan_path after processing all tasks
- `Tester.execute(sprint_plan_path)` → returns "TEST_REPORT.md"
- `Reviewer.execute(sprint_plan_path, test_report_path)` → returns "REVIEW.md"
- `Deployer.execute(review_path)` → returns "DEPLOY.md"

## Wired vs. stubbed

**Wired (249 tests pass):**
- `parse_tasks` — parses tasks in order with id, name, deps, body, criteria, evidence
- `slice_task` — returns task section + Architecture Decisions header
- `apply_evidence_patch` — ticks checkboxes and inserts outputs idempotently
- `Coder._topological_sort` — dependency-ordered task execution
- `Coder._parse_patch` — 3-tier JSON robustness (strict → re-prompt → regex fallback)
- `Tester._verify_task` — calls LLM, parses markdown result, writes TEST_REPORT.md
- `Tester._parse_result` — extracts VERIFIED/MISMATCH/RERUN_FAILED status
- `Reviewer._parse_result` — extracts per-criterion PASS/FAIL/CONCERN/CRITICAL
- `Reviewer._get_git_diff_summary` — subprocess git diff --stat
- `Deployer._detect_deploy_configs` — scans for Dockerfile, docker-compose, fly.toml, etc.
- `Deployer._detect_env_vars` — grep os.environ/os.getenv patterns, skips hidden dirs

**Stubbed:**
- `Tester._run_cmd` — shell command executor (exists but not used in LLM-based flow)
- No real llama-server integration (all tests mock `LLMClient`)
- No `UpstreamPool` with PRIMARY/ALIEN routing (Phase 5)
- No `State` phase tracking integration (Phase 5)
- No human gate approval (Phase 5)
- No git operations (commit, tag, rollback) — Phase 5 orchestrator
- No event bus for PWA streaming (Phase 5)

## Known gaps / deferred

Phase 5 (Orchestrator, `phase-5-orchestrator.md`) needs:
- `UpstreamPool` with PRIMARY/ALIEN endpoint routing and fallback
- `State` phase tracking (`current_phase`, `retries`, `gates_approved`)
- Validators per phase (Tester returns VERIFIED → orchestrator commits)
- Human gate integration (approve_sprint_plan, approve_review)
- Git operations: `git add -A && git commit`, annotated tags, rollback
- Event bus for PWA SSE streaming
- Context budget enforcement (token counting, reasoning strip)
- Queue design for single `-np 1` server slot

## Anything the next phase must know

- **`BaseRole` constructor**: `__init__(self, llm: LLMClient, state: State)` — no `config` param. Roles that need config should accept it separately.
- **`BaseRole._chat`**: takes `messages: list[dict]` directly (not system/user split). Each role constructs the full messages array.
- **`BaseRole._load_prompt`**: loads from `orchestrator/roles/prompts/<role>/<name>.txt` relative to the roles module directory.
- **`Tester` only verifies tasks with `[x]` evidence entries** — tasks with `[ ]` (unchecked) are skipped. This is intentional: the Coder fills `[ ]` with evidence, the Tester only re-verifies what the Coder claims is done.
- **`Tester._write_report`** updates the sprint plan with "Verified by Tester" entries for VERIFIED tasks.
- **`Reviewer._parse_result`** normalizes "APPROVED WITH NOTES" → "APPROVED_WITH_NOTES" for programmatic use.
- **`Deployer._detect_env_vars`** skips `.hidden/`, `.venv/`, `__pycache__/`, `node_modules/`. Uses named capture groups `(?:^|[^a-zA-Z0-9_])(?P<var>NAME)(?:[^a-zA-Z0-9_]|$)` for word patterns to avoid false positives.
- **Phase 4 commits**: `7730170` (T1), `01ecf11` (T2), `1b8be2c` (T3), `76611ba` (T4), `dc86291` (T5)
