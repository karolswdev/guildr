# Phase 2: Ingestion — `qwendea.md` + Quiz

Produce a well-formed `qwendea.md` for every project, either by reading
one the user provides or by running an interactive quiz **in the PWA**.

## Key shift from original plan

The quiz is **PWA-native**, not driven through `opencode run`.
`opencode run` is non-interactive — you can't stream a question and wait
for a user answer through it. The PWA asks questions directly (over
WebSocket / SSE), collects answers, and only hits the LLM for two
purposes:

1. **Adaptive follow-up selection** (after N turns, ask Qwen "given
   these answers, what's the highest-value next question, or is 'none'
   enough?").
2. **Synthesis** — take the Q&A log and produce `qwendea.md`.

## Dependencies

- Phase 1: `LLMClient`, `State`, `Config`.

## Design

### `orchestrator/ingestion/quiz.py`

```python
@dataclass
class QAPair:
    question: str
    answer: str

class QuizEngine:
    def __init__(self, llm: LLMClient, config: Config):
        self.llm = llm
        self.config = config
        self.qa: list[QAPair] = []

    def seed_questions(self) -> list[str]:
        """Static seed — always asked in order before adaptive."""
        return [
            "What are you trying to build? Describe it in your own words.",
            "Who is this for? What problem does it solve?",
            "What are the top 3 features that MUST work for this to succeed?",
        ]

    def next_question(self) -> str | None:
        """Return the next question to ask, or None if done."""
        if len(self.qa) < len(self.seed_questions()):
            return self.seed_questions()[len(self.qa)]

        if len(self.qa) >= self.config.quiz_max_turns:
            return None

        # Adaptive: ask LLM what to ask next, or "DONE"
        return self._adaptive_next()

    def record_answer(self, answer: str) -> None:
        """Attach the user's answer to the most-recently-asked question."""
        ...

    def synthesize(self) -> str:
        """Call LLM to produce qwendea.md from the Q&A log."""
        ...

    def _adaptive_next(self) -> str | None:
        """Ask LLM for the next question OR 'DONE' if sufficient info."""
        ...
```

### `_adaptive_next` prompt shape

```text
You are helping gather software requirements. Below is the Q&A collected
so far. Based on it, either:

(a) Output EXACTLY the next question to ask the user, on one line, with
    no preamble, no quotes, no explanation. The question should probe
    the weakest area (most ambiguity, biggest unknown).

(b) If the answers are sufficient to write a clear requirements document
    covering description, users, core requirements, constraints, and
    out-of-scope, output EXACTLY: DONE

Q&A so far:
<numbered log>
```

Parse: if output trimmed equals `DONE`, stop quiz. Otherwise treat as
next question.

### `synthesize()` prompt shape

```text
You are a requirements analyst. Produce a clean qwendea.md from the
following Q&A.

<Q&A log>

Produce ONLY the markdown file content, with this EXACT structure:

# Project: <Name>

## Description
...

## Target Users
...

## Core Requirements
1. ...

## Constraints
- ...

## Out of Scope
- ...

Rules:
- Every core requirement must be specific and testable
- Avoid vague language ("user-friendly", "fast", "robust") — if you use
  it, give a measurable threshold
- If information is missing for a section, write "TBD" — do NOT invent
```

Post-process the output:
- Strip code fences if the model wraps it.
- Validate it contains all 5 required section headers.
- If missing headers: treat as content failure, retry once with the
  missing-headers list in the feedback.

## PWA interaction (summary; detail in phase 6)

PWA side:
- Displays current question, records answer, posts to backend.
- Shows progress: "question 4 of at most 10".
- Lets user edit any prior answer (go back).
- Final screen: shows generated `qwendea.md`, lets user edit before
  committing.

Backend endpoints (to be implemented in phase 6):
- `POST /projects/{id}/quiz/answer` — submit answer, returns next
  question or `{"done": true, "qwendea": "..."}`.

## Tasks

### Task 1: `QuizEngine` seed + adaptive loop
- **Priority**: P0
- **Dependencies**: Phase 1 complete
- **Files**: `orchestrator/ingestion/quiz.py`, `tests/test_quiz.py`

**Acceptance Criteria:**
- [ ] Returns seed questions in order for the first 3 turns
- [ ] Calls LLM for adaptive questions from turn 4 onward
- [ ] Stops on `DONE` or `quiz_max_turns`
- [ ] Answer history preserved in order

**Evidence Required:**
- `pytest tests/test_quiz.py -v`
- Mock LLM returning `DONE` after 5 turns → quiz stops at turn 5

### Task 2: `synthesize()` + validator
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/ingestion/quiz.py`, `tests/test_synthesize.py`

**Acceptance Criteria:**
- [ ] Produces markdown with all 5 required headers
- [ ] Retries once on missing-header output with targeted feedback
- [ ] Strips wrapping code fences if present
- [ ] On second failure, raises `SynthesisError` with the bad output

**Evidence Required:**
- Mock LLM returning malformed output → retry → valid output → passes
- Mock LLM returning malformed output twice → `SynthesisError` raised

### Task 3: `_ensure_qwendea()` entry point
- **Priority**: P0
- **Dependencies**: Task 2
- **Files**: `orchestrator/ingestion/ensure.py`,
  `tests/test_ensure_qwendea.py`

**Acceptance Criteria:**
- [ ] If `qwendea.md` exists: read, validate structure, return content
- [ ] If missing: expose a `QuizSession` object the PWA can drive
- [ ] On PWA session completion, write `qwendea.md` to `project_dir`
- [ ] Existing `qwendea.md` with missing headers → raise
  `InvalidQwendea` with specific missing headers

**Evidence Required:**
- `pytest tests/test_ensure_qwendea.py -v`
- End-to-end test with a scripted answer sequence

## Phase exit criteria

- All 3 tasks have filled Evidence Logs verified by Tester.
- Given a fixture of 5 scripted answers, `QuizEngine` → `synthesize()`
  produces a valid `qwendea.md` on the real llama-server.

## What's next

Phase 3 (`phase-3-architect.md`) consumes `qwendea.md`.
