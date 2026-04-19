# Phase 3: Architect with Self-Evaluation Loop

The heart of the system. The Architect turns `qwendea.md` into a
`sprint-plan.md` that passes a 6-criterion rubric. If the first draft
fails, it retries with targeted corrective feedback. Up to 3 passes,
then escalate to human.

## Dependencies

- Phase 1: `LLMClient`, `State`
- Phase 2: `qwendea.md` exists

## The 6 criteria

| # | Criterion     | Pass                                                          | Fail looks like                                                      |
|---|---------------|---------------------------------------------------------------|----------------------------------------------------------------------|
| 1 | Specificity   | ≥80% of requirements unambiguous                              | "user-friendly", "fast", "robust" without metrics                    |
| 2 | Testability   | Every acceptance criterion maps to a test or verification     | "looks good", "works well"                                           |
| 3 | Evidence      | Every task has `Evidence Required:` with commands/paths       | Missing sections or generic "prove it works"                         |
| 4 | Completeness  | Every `qwendea.md` requirement maps to ≥1 task                | Orphaned requirements                                                |
| 5 | Feasibility   | No circular deps; scope fits a sprint; ≤3 P0 tasks            | Impossible deps, too many P0s, missing infra tasks                   |
| 6 | Risk          | ≥3 risks identified with concrete mitigations                 | No risk analysis, or risks without mitigation                        |

**Scoring**: each criterion scores 0 or 1. Total out of 6.

**Threshold**: pass if score ≥ 4 AND criteria 2 (Testability) AND 3
(Evidence) both pass. **Mandatory-pass on 2 & 3** because the whole
downstream pipeline depends on them — a plan that fails either is
structurally broken regardless of its other scores.

## The self-eval judge prompt (adversarial)

Same Qwen instance, different system prompt. Key framing:

```text
You are a SKEPTICAL senior engineering manager reviewing a junior's
sprint plan. Your reputation depends on catching sloppy work before it
reaches the team. Assume the junior is trying to get away with vague
language. For each criterion, look for the WORST example, not the
average. A single vague acceptance criterion is enough to fail
Testability. A single task without Evidence Required is enough to fail
Evidence.

Score only 0 or 1 per criterion — no partial credit.

Return ONLY valid JSON matching this schema:
{
  "specificity":  {"score": 0|1, "issues": ["..."]},
  "testability":  {"score": 0|1, "issues": ["..."]},
  "evidence":     {"score": 0|1, "issues": ["..."]},
  "completeness": {"score": 0|1, "issues": ["..."]},
  "feasibility":  {"score": 0|1, "issues": ["..."]},
  "risk":         {"score": 0|1, "issues": ["..."]}
}

<qwendea.md>
<sprint-plan.md>
```

JSON parsing: try strict parse → on failure, re-prompt with "your last
output was not valid JSON, return only the object" → on failure,
regex-extract outermost `{...}` and try again → on final failure, treat
as content failure for the pass.

## Corrective retry prompt

When a pass fails, the next pass sees only:

```text
You are the Architect. Your previous sprint-plan.md failed evaluation on:

FAILED: [Testability] — 3 acceptance criteria are not verifiable:
  - Task 2: "The API should be fast" → needs measurable latency threshold
  - Task 4: "UI should be responsive" → needs specific breakpoint/behavior
  - Task 6: "Data should be secure" → needs specific encryption/auth

FAILED: [Evidence] — 2 tasks have no Evidence Required section:
  - Task 3: Missing test command
  - Task 5: Missing git diff location

Revise sprint-plan.md addressing ONLY these failures. Keep all passing
sections unchanged.

<current sprint-plan.md>
```

**Do NOT include the prior turn's `reasoning_content`** in the messages
array — strip it. See `reference/upstream-contract.md`.

## Design

### `orchestrator/roles/architect.py`

```python
class ArchitectFailure(Exception): ...

class Architect:
    EVALUATION_CRITERIA = [
        "specificity", "testability", "evidence",
        "completeness", "feasibility", "risk",
    ]
    MANDATORY = {"testability", "evidence"}

    def __init__(self, llm: LLMClient, state: State, config: Config):
        ...

    def execute(self) -> str:
        """Run the self-eval loop. Returns path to sprint-plan.md on
        success. Raises ArchitectFailure on exhaustion."""
        qwendea = self.state.read_file("qwendea.md")

        best_plan, best_score = None, 0
        best_eval = None
        drafts = []  # list of (plan, score, eval) — for escalation

        for pass_num in range(1, self.config.architect_max_passes + 1):
            if pass_num == 1:
                plan = self._generate(qwendea)
            else:
                plan = self._refine(qwendea, best_plan, best_eval)

            score, evaluation = self._self_evaluate(qwendea, plan)
            drafts.append((plan, score, evaluation))

            if self._passes(score, evaluation):
                self.state.write_file("sprint-plan.md", plan)
                return "sprint-plan.md"

            if score > best_score:
                best_plan, best_score, best_eval = plan, score, evaluation

        self._escalate(drafts)
        raise ArchitectFailure(
            f"Architect failed after {self.config.architect_max_passes} "
            f"passes (best score: {best_score}/6)"
        )

    def _passes(self, score: int, evaluation: dict) -> bool:
        if score < self.config.architect_pass_threshold:
            return False
        return all(evaluation[c]["score"] == 1 for c in self.MANDATORY)

    def _generate(self, qwendea: str) -> str: ...
    def _refine(self, qwendea: str, prior: str, prior_eval: dict) -> str: ...
    def _self_evaluate(self, qwendea: str, plan: str) -> tuple[int, dict]: ...
    def _escalate(self, drafts: list) -> None: ...
```

Prompt templates: kept in `orchestrator/roles/prompts/architect/*.txt`,
loaded at startup. No string concatenation inline — keeps them
reviewable.

### Escalation path

When all passes fail:
1. Write all drafts to `.orchestrator/drafts/architect-pass-{1,2,3}.md`.
2. Write the final evaluation JSONs alongside.
3. Write a human-readable summary to `.orchestrator/escalation.md`
   listing what failed across passes and which criteria never improved.
4. Orchestrator halts and surfaces the escalation to the PWA.

## Tasks

### Task 1: Prompt templates
- **Priority**: P0
- **Files**: `orchestrator/roles/prompts/architect/{generate,refine,judge}.txt`

**Acceptance Criteria:**
- [ ] `generate.txt` includes the full `sprint-plan.md` structure
      specification from `01-conventions.md`
- [ ] `judge.txt` includes the skeptical framing and the strict JSON
      schema
- [ ] `refine.txt` references `{failures}` and `{current_plan}` slots
      only — no extra context

**Evidence Required:**
- Visual inspection via `cat`
- `grep "Evidence Required" orchestrator/roles/prompts/architect/generate.txt`

### Task 2: `_generate` and `_refine`
- **Priority**: P0
- **Dependencies**: Task 1, Phase 1
- **Files**: `orchestrator/roles/architect.py`,
  `tests/test_architect_gen.py`

**Acceptance Criteria:**
- [ ] `_generate` produces a markdown string with all sprint-plan
      headers
- [ ] `_refine` strips prior reasoning from the messages array
- [ ] `_refine` injects only the failed-criteria feedback, not the full
      evaluation JSON

**Evidence Required:**
- `pytest tests/test_architect_gen.py -v`
- Message-array inspection: mock LLM, capture the `messages`
  parameter, assert no `reasoning_content` field present

### Task 3: `_self_evaluate` with JSON robustness
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/roles/architect.py`,
  `tests/test_architect_judge.py`

**Acceptance Criteria:**
- [ ] Strict JSON parse succeeds on well-formed output
- [ ] Re-prompt on malformed → success on retry
- [ ] Regex fallback extracts outermost `{...}` block
- [ ] After 2 failed reparse attempts, returns score 0 with
      `{"reason": "malformed"}`

**Evidence Required:**
- `pytest tests/test_architect_judge.py -v`
- Test fixtures: valid JSON, JSON with prose wrapper, JSON with
  trailing junk, completely malformed

### Task 4: Pass/fail logic with mandatory criteria
- **Priority**: P0
- **Dependencies**: Task 3
- **Files**: `orchestrator/roles/architect.py`,
  `tests/test_architect_passes.py`

**Acceptance Criteria:**
- [ ] Score 5/6 with Testability=0 → FAIL (mandatory)
- [ ] Score 5/6 with Evidence=0 → FAIL (mandatory)
- [ ] Score 4/6 with Testability=1 AND Evidence=1 → PASS
- [ ] Score 6/6 → PASS
- [ ] Score 3/6 with all mandatory=1 → FAIL (below threshold)

**Evidence Required:**
- `pytest tests/test_architect_passes.py -v` covering all 5 cases

### Task 5: Escalation
- **Priority**: P1
- **Dependencies**: Task 4
- **Files**: `orchestrator/roles/architect.py`,
  `tests/test_architect_escalate.py`

**Acceptance Criteria:**
- [ ] Writes all drafts to `.orchestrator/drafts/`
- [ ] Writes evaluation JSONs alongside
- [ ] Writes human-readable `.orchestrator/escalation.md`
- [ ] Raises `ArchitectFailure` with best score in the message

**Evidence Required:**
- `pytest tests/test_architect_escalate.py -v`
- File-existence assertions after forced 3-pass failure

## Phase exit criteria

- All tasks' Evidence Logs verified.
- End-to-end on real llama-server: given a simple `qwendea.md`
  (e.g., "Build a REST API for a todo app"), architect produces a
  passing `sprint-plan.md` in ≤2 passes.
- End-to-end on a deliberately ambiguous `qwendea.md`, architect either
  converges in ≤3 passes OR escalates cleanly.

## What's next

Phase 4 (`phase-4-roles.md`) — Coder consumes `sprint-plan.md`.
