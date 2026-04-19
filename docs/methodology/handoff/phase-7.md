# Phase 7 Handoff

## What this phase actually built

### Key files and modules

**Structured logging** (Task 1):
- `orchestrator/lib/logger.py` — JSONL log format, per-phase files, LLM call instrumentation
- All roles (`architect`, `coder`, `tester`, `reviewer`, `deployer`) updated to accept `phase_logger` and log LLM calls

**Dry-run mode** (Task 3):
- `orchestrator/lib/llm_fake.py` — `FakeLLMClient` with canned responses keyed by role
- `orchestrator/engine.py` — `fake_llm` parameter, `is_dry_run()` method, role methods use fake when set
- `tests/test_dry_run.py` — 14 tests covering fake client and orchestrator integration

**Session inspection CLI** (Task 4):
- `orchestrator/cli/__init__.py` — package marker
- `orchestrator/cli/inspect.py` — CLI with `inspect` subcommand:
  - `orchestrator inspect <project-id>` — lists phases + status
  - `--phase NAME` — dumps session transcript
  - `--tokens` — shows per-phase token usage
- `tests/test_inspect.py` — 17 tests

**Documentation** (Task 5):
- `README.md` — install, quickstart, architecture overview, testing
- `docs/getting-started.md` — end-to-end walkthrough
- `docs/architecture.md` — system design summary
- `docs/examples/todo-app/` — complete example project fixture

### Entry points

- `python -m orchestrator.cli inspect <project>` — CLI entry
- `Orchestrator(config, fake_llm=fake)` — dry-run entry
- `FakeLLMClient(responses={...})` — fake client factory

## Wired vs. stubbed

**Wired (end-to-end):**
- Structured logging works: `setup_phase_logger()` creates JSONL files, `log_llm_call()` records token counts and latency
- Dry-run mode: `FakeLLMClient` returns canned responses, orchestrator uses it when `fake_llm` is set, all 14 tests pass
- CLI inspection: lists phases, dumps sessions, shows token usage — all 17 tests pass
- Documentation: all files created and structurally complete

**Stubbed / deferred:**
- Task 2 (Metrics gauges in PWA): Not implemented — frontend TypeScript component `web/frontend/src/components/Metrics.ts` needed
- Task 6 (Parallel coder tasks): Deferred as P3 optional
- The `--dry-run` flag is available via programmatic API (`fake_llm` parameter) but not yet exposed as a CLI flag
- No `markdownlint` setup for docs validation (requires external tool)

## Known gaps / deferred

- **No CLI `--dry-run` flag**: Dry-run works via `Orchestrator(fake_llm=fake)` but not via `python -m orchestrator.cli --dry-run`. Next phase should add the CLI flag.
- **No CI integration for dry-run**: Tests exist in `tests/test_dry_run.py` but CI pipeline doesn't run them automatically.
- **No push notifications**: Not implemented in PWA.
- **No multi-project support**: ProjectStore is flat (single active project).
- **No gate auto-creation**: Gates are not created by orchestrator runs (Phase 6 gap carried forward).
- **No SSE integration**: Phase 5 EventBus not wired to PWA SimpleEventBus (Phase 6 gap carried forward).
- **markdownlint not configured**: Documentation passes manual review but has no automated lint check.

## Anything the next phase must know

- **Config has no `logging.level` field**: The logger tests verify configurable log level via `setup_phase_logger(project_dir, phase, level=logging.DEBUG)`, but `Config` dataclass doesn't have a `logging.level` attribute. The acceptance criterion "Log level configurable via `config.logging.level`" is not met — this needs to be added to Config.
- **Engine role methods accept `fake_llm` or `pool.chat`**: The role methods check `self._fake_llm or (self._pool.chat if self._pool else None)`. This means `fake_llm` takes priority over the pool. When both are set, dry-run wins.
- **FakeLLMClient extracts role from last message**: It looks at the last message's `role` field (user/assistant/system) and falls back to "default". This works for most orchestrator prompts but may need adjustment if prompt structure changes.
- **CLI `find_project()` checks three locations**: Direct path, `~/.orchestrator-projects/`, `/tmp/orchestrator-projects/`. If projects are stored elsewhere, add it to the list.
- **Token counting in CLI only counts `llm_call.*` events**: The `--tokens` flag filters by `event.startswith("llm_call")`. Non-LLM log entries (phase_start, phase_done, etc.) are excluded.
- **Git history**: Phase 7 commits since phase start (242bf11):
  - `ad97088` — task-1: structured logging
  - `9166548` — task-1: Evidence Log SHA update
  - `1144d7f` — task-3: dry-run mode
  - `141e130` — task-4: session inspection CLI
  - `e98c525` — task-5: documentation
  - `2d8d4ae` — prepare: sprint plan update
