# Context Budget Policy

Qwen3.6 has a 131072-token context window. That's generous, but architect
self-eval loops + preserved thinking tokens + large code context can add
up. Budget explicitly.

## Per-call soft caps

| Component                                                   | Target    | Hard cap |
|-------------------------------------------------------------|-----------|----------|
| System prompt + role framing                                | ≤ 2K tok  | 4K       |
| Design docs (00-overview + phase file + relevant reference) | ≤ 8K tok  | 12K      |
| Task-specific context (sprint-plan slice, code files)       | ≤ 30K tok | 60K      |
| Prior-turn reasoning (stripped on refine)                   | 0         | 0        |
| Reserved for generation                                     | ≥ 16K tok | —        |

**Total input budget per call: ~50K tokens.** Leaves headroom for
thinking + output.

## Slice, don't paste

- **Coder**: receive only the current task's section from sprint-plan.md
  (plus the `## Architecture Decisions` header), never the whole plan.
  Implement `slice_task(sprint_plan_md, task_id) -> str`.
- **Tester**: receive only tasks whose Evidence Log is filled, with
  their Evidence Required. Not the whole file.
- **Reviewer**: receive sprint-plan's acceptance-criteria checklist +
  git diff summary, not every file's full contents.
- **Architect refine**: receive the current draft + targeted failure
  feedback only. Not the full conversation history.

## Evidence Log writes are append-only patches

Do not round-trip the entire `sprint-plan.md` through the model to tick
one checkbox. The Coder emits a structured patch:

```json
{
  "task_id": 3,
  "entries": [
    {"check": "Test command run", "output": "...", "passed": true},
    {"check": "Git diff in lib/state.py", "passed": true}
  ]
}
```

A deterministic Python function applies this to `sprint-plan.md` outside
the model. Keeps Coder prompts under ~15K tokens even late in a sprint.

## Reasoning-token accounting

With `preserve_thinking: true`, `reasoning_content` stays in responses
and can be tens of thousands of tokens on hard problems. When building
the next turn's messages:

- **Strip reasoning from assistant messages being resent** (see
  `upstream-contract.md`).
- **Keep reasoning in session transcripts** (exported to
  `.orchestrator/sessions/` for debugging), but NOT in the live prompt.

## Monitoring

Every call logs:

- `prompt_tokens`, `completion_tokens`, `reasoning_tokens` (from the
  server's `/v1/chat/completions` `usage` block).
- Running total per phase.

If any single call crosses **70K input tokens**, log a warning. If it
crosses 100K, **refuse to send** and surface to the PWA — something in
the slicing logic is broken.
