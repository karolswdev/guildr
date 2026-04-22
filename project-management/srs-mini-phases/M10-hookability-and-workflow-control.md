# M10 — Hookability And Workflow Control

## Purpose

Make the engine aggressively hookable: configured interception points can observe, modify, approve, block, or add work — including guru escalation through Codex/Claude/OpenRouter. Workflow is durable JSON, editable in the PWA, and every hook output lands in the event ledger.

## Why this phase exists

SRS §7 Hookability is load-bearing for the "batteries provided, boundaries programmable" principle (§4.10). Without hooks, operators cannot extend the engine without code changes. Without bounded guru escalation, repair loops are ad-hoc. SRS §6.5, §11.

## Required context files

- `docs/srs-council-engine.md` §4.10, §6.5, §7, §11
- `orchestrator/lib/workflow.py`
- `orchestrator/lib/control.py`
- `config.example.yaml` (`endpoints:` + `routing:` block)
- `QUALITY_GATES.md` G1, G8

## Implementation surface

- `orchestrator/lib/hooks.py` (hook registry, sandbox contract)
- `orchestrator/lib/escalation.py` (advisor call, bounded packet, plan parser, remediation decomposer)
- Workflow JSON schema: `hooks[]` per step, `atom` metadata fields (inputs/memory/output/evidence/acceptance/retry/blast_radius)
- Events: `hook_triggered`, `hook_effect_applied`, `advisor_called`, `advisor_plan_received`, `advisor_task_decomposed`
- PWA workflow editor: hook inspector, permission chips, sandbox state
- Advisor providers: `codex` CLI, `claude` CLI, OpenAI-compatible, OpenRouter (H5.2 `endpoints:` reused)

## Tasks

- [ ] Define hook point enum matching SRS §7 (before_step, after_step, on_phase_failure, before_retry, before_context_compaction, after_memory_refresh, before/after_advisor_escalation, before_gate, after_gate_decision, before_file_write, after_test_run, before_deployment).
- [ ] Hook capability enum (observe, add_instruction, mutate_config, add_checkpoint, trigger_memory_search, trigger_memory_sync, request_escalation, block_with_gate, write_artifact, emit_custom_event).
- [ ] Sandbox contract: hook config declares allowed capabilities; engine rejects capability use not declared.
- [ ] Persist hook config in workflow JSON; expose via existing workflow GET/PUT route.
- [ ] Emit `hook_triggered` before execution, `hook_effect_applied` after, both referencing `hook_id` and `step_id`.
- [ ] Guru escalation path: role-agnostic advisor call gets a compact packet, returns remediation plan, plan decomposes into atomic verifiable steps.
- [ ] Support advisor types: `codex` CLI, `claude` CLI, OpenAI-compatible, OpenRouter — reuse `endpoints:` + `routing:` config.
- [ ] Advisor output written as artifact; `advisor_called` / `advisor_plan_received` events carry artifact ref + cost.
- [ ] Workflow editor in PWA: drag reorder steps, toggle enable, add checkpoint, inspect hooks, scope instructions to phases. Must remain a map-integrated panel, not a full page.
- [ ] Atom metadata (§6.2) derivable: inputs consumed, memory used, output artifact, event span, acceptance criteria, evidence required, retry policy, hook points.

## Quality gates

- [ ] G1 Event integrity on hook + advisor events.
- [ ] G8 Security — hooks are sandbox-aware; cannot silently read secrets or write outside project.
- [ ] G7 Cost truth — every advisor call emits `usage_recorded`.
- [ ] G4 No-dashboard — workflow editor is a lens/panel, not a tabbed admin console.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_hooks.py tests/test_escalation.py tests/test_workflow_editor.py
uv run pytest -q tests/test_integration_advisor_openrouter.py   # mocked
./web/frontend/build.sh
```

## Done means

- [ ] Hook points fire at every SRS §7 location; registry shows each firing.
- [ ] Sandbox refuses undeclared capability use with a loud event.
- [ ] Advisor (codex/claude/OpenRouter/OpenAI-compatible) reachable via config, not code change.
- [ ] Advisor plans are decomposed into atomic remediation tasks.
- [ ] Workflow editor can toggle/reorder/add-checkpoint from the map; changes durable across reload.

## Known traps

- A hook with write capability that touches paths outside the project — enforce relative path + allow-list.
- Storing advisor API keys in workflow JSON — always resolve via `api_key_env` indirection (reuse H5.2 pattern).
- Hook re-entrancy: a hook that triggers another hook that triggers the first. Detect cycle, emit `hook_rejected`, break.
- Advisor plans with unbounded output — cap tokens; summarize rather than re-inject whole.

## Handoff notes

- M09 relies on advisor emission path for `usage_recorded` coverage.
- M11 tests replay-resilience when a hook or advisor call crashes mid-run.
