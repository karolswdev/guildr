# Phase 3: Architect with Self-Evaluation Loop — Handoff

## What this phase built

**`orchestrator/roles/architect.py`** — Full `Architect` dataclass implementing:

- **`execute()`** — The self-eval loop: generates a plan, evaluates it against 6 criteria, retries with targeted feedback up to `config.architect_max_passes` times, or escalates.
- **`_generate(qwendea)`** — Calls LLM with `generate.txt` prompt to produce initial sprint-plan.md.
- **`_refine(qwendea, prior, prior_eval)`** — Strips prior reasoning_content from messages, injects only failed-criteria feedback via `refine.txt`.
- **`_self_evaluate(qwendea, plan)`** — Adversarial judge: calls LLM with `judge.txt`, parses JSON with 3-tier robustness (strict → re-prompt → regex fallback).
- **`_passes(score, evaluation)`** — Score ≥ threshold AND all MANDATORY criteria (testability, evidence) = 1.
- **`_escalate(drafts)`** — Writes draft files, eval JSONs, and human-readable escalation.md to `.orchestrator/`.

**`orchestrator/roles/prompts/architect/`** — Three prompt templates:
- `generate.txt` — Full sprint-plan.md structure specification
- `judge.txt` — Skeptical framing + strict JSON schema
- `refine.txt` — `{failures}` and `{current_plan}` slots only

**Tests**: 50 tests across 4 files:
- `tests/test_architect_gen.py` (8 tests) — _generate and _refine
- `tests/test_architect_judge.py` (17 tests) — _self_evaluate with JSON robustness
- `tests/test_architect_passes.py` (12 tests) — pass/fail logic
- `tests/test_architect_escalate.py` (13 tests) — escalation + execute

## Wired vs. stubbed

**Wired (50 tests pass):**
- `_generate` sends system + user prompts, returns LLM content
- `_refine` strips reasoning_content, injects targeted feedback
- `_self_evaluate` with 3-tier JSON parsing (strict → re-prompt → regex → score 0)
- `_passes` with mandatory criteria enforcement
- `_escalate` writes drafts, evals, escalation.md
- `ArchitectFailure` raised on exhaustion with best score

**Stubbed:**
- No real llama-server integration (all tests mock `LLMClient`)
- No `slice_task` helper for Coder (Phase 4)
- No Evidence Log patch JSON applier (Phase 4)
- No `State` phase tracking integration (Phase 5 orchestrator)
- No human gate approval (Phase 5)

## Known gaps / deferred

Phase 4 (Coder) needs:
- `slice_task(sprint_plan_md, task_id) -> str` — context slicing
- Evidence Log patch JSON applier — deterministic file writer
- `BaseRole` pattern shared across roles
- Context budget enforcement (strip reasoning, token counting)

Phase 5 (Orchestrator) needs:
- `State` phase tracking (`current_phase`, `retries`)
- Upstream pool (`UpstreamPool` with PRIMARY/ALIEN)
- Validators per phase
- Human gate integration
- Git operations (commit, tag, rollback)
- Event bus for PWA streaming

## Anything the next phase must know

- **`Architect` is a dataclass** with `llm`, `state`, `config` as constructor args. The `EVALUATION_CRITERIA` and `MANDATORY` are dataclass fields (not class-level), so they're instance attributes.
- **`_format_failures` is an instance method** (not static) — it accesses `self.EVALUATION_CRITERIA`.
- **`_passes` handles both dict and int evaluation entries** — the `_compute_score` output is always dict-format, but tests may pass int-format. The `_make_eval` helper in tests uses ints.
- **Prompt templates are loaded at call time** (not cached) from `orchestrator/roles/prompts/architect/`. Path is relative to the module file.
- **`execute()` requires `qwendea.md` to exist** in `state.project_dir` — it calls `self.state.read_file("qwendea.md")` before any LLM calls.
- **Phase 3 commits**: `485289f` (T1), `3a774d3` (T2), `17d08e9` (T3), `7731097` (T4), `44fcf1b` (T5)
