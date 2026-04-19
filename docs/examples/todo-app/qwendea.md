# Project: Todo App CLI

## Description
A command-line todo list manager that supports adding, listing, completing,
and deleting tasks. Data persists in a JSON file.

## Target Users
Individuals who want a simple, fast todo list without opening a browser.

## Core Requirements
1. `todo add <task>` — adds a new task
2. `todo list` — shows all tasks with status (pending/done)
3. `todo done <id>` — marks a task as completed
4. `todo delete <id>` — removes a task
5. Data persists in `~/.todo/data.json`
6. Exit code 0 on success

## Constraints
- Python 3.12+
- No external dependencies (stdlib only)
- JSON file format for persistence

## Out of Scope
- Web interface
- Sync across devices
- Tags or categories
- Due dates
