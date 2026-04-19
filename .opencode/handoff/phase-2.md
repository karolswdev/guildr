# Phase 2: Ingestion — Handoff

## What this phase built

Two modules under `orchestrator/ingestion/`:

- **`quiz.py`** — `QuizEngine` drives interactive Q&A: 3 seed questions,
  then adaptive LLM follow-ups. `synthesize()` produces `qwendea.md`
  from Q&A log with code-fence stripping, header validation, and one
  retry. Raises `SynthesisError` on second failure.

- **`ensure.py`** — `_ensure_qwendea()` entry point: reads existing
  `qwendea.md` (validates headers, returns content or raises
  `InvalidQwendea`), or returns a `QuizSession` for PWA-driven quiz.
  `complete_quiz()` writes synthesized output to disk.

Key entry points: `QuizEngine(llm, config)`, `QuizSession(engine)`,
`_ensure_qwendea(project_dir, llm, config)`, `complete_quiz(session, dir)`.

## Wired vs. stubbed

**Wired (40 tests pass):** QuizEngine seed/adaptive loop, synthesize
with retry, QuizSession delegation, `_ensure_qwendea()` existence
check, `complete_quiz()` write, `SynthesisError`, `InvalidQwendea`.

**Stubbed:** No PWA frontend (Phase 6), no HTTP endpoints, no quiz
state persistence between requests, no real llama-server integration
(gated on `LLAMA_SERVER_URL`).

## Known gaps / deferred

Phase 3 (Architect) needs: a concrete `qwendea.md` to consume,
`sprint-plan.md` task slicer (`slice_task`), Evidence Log patch JSON
applier, and the `State` class.

Phase 6 (PWA) needs: FastAPI quiz endpoints, state persistence,
SSE/WebSocket streaming.

## Anything the next phase must know

- **`REQUIRED_HEADERS`** (6 headers) is in `quiz.py`. Both
  `_ensure_qwendea()` and `QuizEngine._check_missing_headers()` use it.
- **`QuizSession` wraps `QuizEngine`** — PWA uses `QuizSession`, not
  the engine directly.
- **`_ensure_qwendea()` returns `str | QuizSession`** — callers must
  check the type. `str` = existing valid file; `QuizSession` = needs quiz.
- **`complete_quiz()` does NOT check existence** — that's
  `_ensure_qwendea()`'s job.
- **LLM temperatures**: synthesis uses `0.3`, adaptive questions use
  `0.7` (hardcoded in `quiz.py`).
- **Phase 2 commits**: `379779d` (T1), `7c3249d` (T2), `0651a81` (T3)
