# Phase 2: Ingestion — Handoff

## What this phase built

Two new modules under `orchestrator/ingestion/`:

- **`orchestrator/ingestion/quiz.py`** — `QuizEngine` class drives an
  interactive Q&A quiz. Seed questions for the first 3 turns, then
  adaptive LLM-driven follow-ups. `synthesize()` calls the LLM to
  produce `qwendea.md` from the Q&A log, with code-fence stripping,
  header validation, and one retry on failure. Raises `SynthesisError`
  on second failure.

- **`orchestrator/ingestion/ensure.py`** — `_ensure_qwendea()` entry
  point that checks if `qwendea.md` already exists (validates headers,
  returns content or raises `InvalidQwendea`), or returns a
  `QuizSession` for the PWA to drive. `complete_quiz()` writes the
  synthesized output to disk.

Entry points:
- `QuizEngine(llm, config)` — construct with LLMClient and Config
- `QuizEngine.seed_questions()` → `list[str]`
- `QuizEngine.next_question()` → `str | None`
- `QuizEngine.record_answer(answer)` → `None`
- `QuizEngine.synthesize()` → `str` (qwendea.md content)
- `QuizSession(engine)` — PWA-facing wrapper
- `QuizSession.next_question`, `.submit_answer()`, `.is_complete`,
  `.synthesize()`, `.qa_log`
- `_ensure_qwendea(project_dir, llm, config)` → `str | QuizSession`
- `complete_quiz(session, project_dir)` → `str`

## Wired vs. stubbed

**Wired (tested, runnable):**
- `QuizEngine` seed questions (3 static, returned in order).
- `QuizEngine.next_question()` — adaptive via LLM after turn 3.
- `QuizEngine.record_answer()` — appends to `self.qa` list.
- `QuizEngine.synthesize()` — LLM call + header validation + retry.
- `QuizSession` — delegates all methods to underlying engine.
- `_ensure_qwendea()` — reads existing qwendea.md or returns QuizSession.
- `complete_quiz()` — synthesizes and writes qwendea.md to disk.
- `SynthesisError` — raised on synthesis failure, includes `bad_output`.
- `InvalidQwendea` — raised on invalid existing qwendea.md, includes
  `missing_headers`.

All 40 tests pass (11 quiz + 11 synthesize + 18 ensure).

**Stubbed / not built:**
- No PWA frontend — `QuizSession` is ready for PWA integration but
  no HTTP endpoints exist yet (Phase 6).
- No `POST /projects/{id}/quiz/answer` endpoint (Phase 6).
- No persistence of quiz state between requests (Phase 6).
- No real llama-server integration (gated on `LLAMA_SERVER_URL`).
- No `_ensure_qwendea()` auto-start of quiz (returns QuizSession, but
  the PWA must drive it).

## Known gaps / deferred

Phase 3 (Architect) needs:
- A concrete `qwendea.md` file in a project directory to consume.
- `sprint-plan.md` task slicer (`slice_task(sprint_plan_md, task_id)`).
- Evidence Log patch JSON applier (phase 3 spec references this).
- The `State` class for tracking phase progress.

Phase 6 (PWA) needs:
- FastAPI endpoints for quiz interaction.
- Quiz state persistence (currently in-memory only via `QuizEngine`).
- SSE/WebSocket streaming for question display.

## Anything the next phase must know

- **`REQUIRED_HEADERS`** is defined in `quiz.py` (6 headers). Both
  `_ensure_qwendea()` and `QuizEngine._check_missing_headers()` use it.
  If headers change, update this constant.

- **`QuizSession` wraps `QuizEngine`** — the PWA interacts with
  `QuizSession`, not `QuizEngine` directly. The engine is internal.

- **`_ensure_qwendea()` returns `str | QuizSession`** — the return type
  is a union. Callers must check which type they got. If `str`, the
  qwendea.md already exists and is valid. If `QuizSession`, the PWA
  needs to drive the quiz.

- **`complete_quiz()` is a standalone function** — it takes a
  `QuizSession` and `project_dir`, synthesizes, and writes. It does
  NOT check if qwendea.md already exists (that's `_ensure_qwendea()`'s
  job).

- **The LLM is called with `temperature=0.3` for synthesis** (creative
  but focused) and `temperature=0.7` for adaptive questions (more
  varied). These are hardcoded in `quiz.py`.

- **Phase 2 commits**:
  - `379779d` — Task 1: QuizEngine seed + adaptive loop
  - `7c3249d` — Task 2: synthesize() + validator
  - `0651a81` — Task 3: _ensure_qwendea() entry point
