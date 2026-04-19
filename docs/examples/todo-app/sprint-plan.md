# Sprint Plan

## Overview
Implement a CLI todo app using Python's argparse and stdlib json module.
Single file implementation with subcommands for add, list, done, and delete.

## Architecture Decisions
- Single file (`todo.py`) for simplicity
- JSON file at `~/.todo/data.json` for persistence
- argparse subcommands for CLI interface

## Tasks

### Task 1: Project setup
- **Priority**: P0
- **Dependencies**: none
- **Files**: `todo/__init__.py`, `todo/cli.py`

**Acceptance Criteria:**
- [ ] `todo add "buy milk"` creates a new task
- [ ] `todo list` shows all tasks

**Evidence Required:**
- Run `python -m todo.cli add "test task"` and verify JSON file created
- Run `python -m todo.cli list` and observe output

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded
- [ ] Git diff verified in `todo/cli.py`
- [ ] Committed as <short-sha>

### Task 2: Complete and delete
- **Priority**: P1
- **Dependencies**: Task 1
- **Files**: `todo/cli.py`

**Acceptance Criteria:**
- [ ] `todo done 1` marks task 1 as completed
- [ ] `todo delete 1` removes task 1
- [ ] `todo list` shows status column

**Evidence Required:**
- Run `python -m todo.cli done 1` and verify task status changed
- Run `python -m todo.cli delete 1` and verify task removed

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded
- [ ] Committed as <short-sha>

## Risks & Mitigations
1. JSON file corruption → Use atomic writes (write to .tmp then rename)
2. Concurrent access → File locking with fcntl (Unix only)
