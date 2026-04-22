# Handover — H6 Opencode Agent Runtime

Last updated: 2026-04-21 (after H6.5 architect plan/refine split).

## Kickoff prompt (copy this into a fresh context)

> You are picking up the `guildr` SDLC orchestrator after H6.5. Working dir is `build/workspace/`. Read `project-management/STATUS.md`, `project-management/phases/harness-6-opencode-agent-runtime.md`, and `project-management/HANDOVER_H6.md` before touching anything — those three files describe the current state, what just landed, and what to do next. The H6 migration moved every SDLC role (architect, judge, coder, tester, reviewer, deployer) off the direct `LLMClient`/pool path onto opencode `SessionRunner`s; pre-phase roles (persona_forum, memory_refresh, guru_escalation) still use `self._llm_for(role)` and are the only remaining pool consumers. H6.5 split the architect phase into `architect_plan` → `approve_plan_draft` (gate) → `architect_refine`, with the gate auto-approving when pass 1 already produced a passing sprint-plan. H6.6 guards the production CLI path with a fake-opencode integration test. Full suite: 561 passed / 1 skipped. Remaining H6 work: **pool-machinery sunset** — delete `SyncPoolClient`, `UpstreamPool`, `LLMClient`, `pool.jsonl`, `pool_log.py`, `sync_pool.py` once the three pre-phase roles move off the pool or are deprecated. Default to terse responses, use options blocks for any question with known answers, and when in doubt prefer editing over creating files. Don't skip hooks, don't force-push, don't commit unless asked.

## Where things stand

| Area | State |
| --- | --- |
| H6.0–H6.2 | Done — opencode subprocess adapter, per-project `opencode.json` generator, `SessionRunner` Protocol |
| H6.3a Coder | Done — `orchestrator/roles/coder.py` + `coder_dryrun.py` |
| H6.3b Tester | Done — `orchestrator/roles/tester.py` + `tester_dryrun.py` |
| H6.3c Reviewer | Done — `orchestrator/roles/reviewer.py` + `reviewer_dryrun.py` |
| H6.3d Deployer | Done — `orchestrator/roles/deployer.py` + `deployer_dryrun.py` |
| H6.3e Architect + Judge | Done 2026-04-21 — `orchestrator/roles/architect.py` + `architect_dryrun.py` |
| H6.4 Audit trail | Done — `orchestrator/lib/opencode_audit.py::emit_session_audit` emits raw-io + usage rows per assistant message |
| H6.5 Gates between sessions | Done 2026-04-21 — architect split into `architect_plan` → `approve_plan_draft` → `architect_refine`; gate auto-approves when pass 1 already passes rubric |
| H6.6 End-to-end guardrail | Done — `tests/test_integration_h6_opencode_pipeline.py` |
| Pool-machinery sunset | Blocked on pre-phase roles migrating or being deprecated |

## Load-bearing invariants worth knowing before editing

- `SessionRunner.run(prompt)` is **stateless by design**. Multi-turn flows (like the judge JSON-repair loop in `architect.py::_self_evaluate`) concatenate prior malformed output into a fresh prompt rather than continuing a session.
- **Gates fire only between phases, never inside a role.** The gate registry is called from `engine._run_gate_or_checkpoint`, never from role code. `approve_plan_draft` auto-approves when `.orchestrator/drafts/architect-plan-status.json` says `status == "done"`, so humans only see it when pass 1 wrote a draft instead of sprint-plan.md.
- Agent tool allowlists live in `opencode_config.py::build_agent_definitions`. Architect + judge have every tool disabled; coder has read/write/edit/glob/grep; tester has bash/read/glob/grep; reviewer + deployer are read-only.
- Dry-run runners under `orchestrator/roles/*_dryrun.py` are what `_build_dry_run_llm`'s consumers used to rely on — the fake LLM is now a vanilla `FakeLLMClient` with no content-aware dispatch.
- `engine.py::_session_runner_for(role)` resolution order: explicit injection → auto-build dry-run runner if `fake_llm` is set → `None` (caller raises `PhaseFailure`).
- In production (`cli/run.py::_build_opencode_session_runners`), the judge role falls back to architect's routing when no explicit `routing.judge` is declared.
- Auditing always fires before any non-zero-exit raise, so failed sessions still leave a trail in `raw-io.jsonl` + `usage.jsonl`.
- Workflow compat: legacy `workflow.json` files carrying a single combined `architect` step keep working — `_merge_missing_default_steps` skips splicing the new plan/approve/refine trio alongside it to avoid double-running.

## Suggested next moves (pick one)

1. **Pool-machinery sunset prep.** Either migrate the three pre-phase roles (persona_forum, memory_refresh, guru_escalation) to opencode agents or collapse their LLM calls into deterministic helpers. Until then, `SyncPoolClient` et al. stay. The H5.3 integration test is already structured to catch regressions in either direction.
2. **Manual/live H2 pickup.** When a human and the LAN endpoint are available, run the manual PWA walk-through and a live endpoint rehearsal; the H6 fake-opencode guard only proves production wiring, not the real model/device path.
3. **PWA plumbing for `approve_plan_draft`.** The new gate emits `gate_opened` / `gate_decided` events like any other, so the existing PWA should render it without changes — but worth a browser smoke-test that the button labels / artifact-path rendering look sensible for the new gate id.

## Useful commands

```
# full suite (expect 561 passed, 1 skipped, ~60s)
python -m pytest

# just H6-shaped tests
python -m pytest tests/test_architect_*.py tests/test_coder.py tests/test_tester.py \
                 tests/test_reviewer.py tests/test_deployer.py tests/test_opencode_*.py \
                 tests/test_integration_h2_1_rehearsal.py tests/test_integration_h5_*.py \
                 tests/test_integration_h6_opencode_pipeline.py
```
