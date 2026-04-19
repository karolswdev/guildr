# Sprint Plan

## Overview
Phase 1 establishes the core infrastructure: LLM client for llama-server communication, project state persistence, and config loading. Phase 2 adds requirements ingestion via an interactive quiz that produces `qwendea.md`.

## Architecture Decisions
- Use the `openai` Python SDK (OpenAI-compatible protocol) for llama-server communication
- JSON-based state persistence with atomic writes (tmp + rename pattern)
- YAML config file with environment variable overrides
- All code in `orchestrator/lib/` package
- Quiz engine in `orchestrator/ingestion/` with adaptive LLM-driven follow-ups

## Tasks

### Task 1: Project skeleton
- **Priority**: P0
- **Dependencies**: none
- **Files**: `orchestrator/__init__.py`, `orchestrator/lib/__init__.py`,
  `pyproject.toml`, `tests/__init__.py`

**Acceptance Criteria:**
- [x] `pip install -e .` succeeds
- [x] `python -c "import orchestrator"` works

**Evidence Required:**
- Run `pip install -e .` and capture success output
- Run `python -c "import orchestrator; print(orchestrator.__file__)"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```Successfully built orchestrator / Successfully installed orchestrator-0.1.0```
- [x] Import verified: `/Users/karol/dev/projects/llm-projects/build/workspace/orchestrator/__init__.py`
- [x] Committed as dd68070


### Task 2: LLM client
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/llm.py`, `tests/test_llm.py`

**Acceptance Criteria:**
- [x] `LLMClient.chat()` parses both `content` and `reasoning_content`
- [x] Mid-thinking truncation raises `ThinkingTruncation`
- [x] `health()` hits `/health` endpoint
- [x] HTTP 5xx triggers exponential backoff (1,2,4,8s; max 4 retries)
- [x] Connection refused raises immediately without retry

**Evidence Required:**
- Run `pytest tests/test_llm.py -v` and observe all tests pass
- Mock llama-server with `respx` or `httpx_mock`; verify retry behavior
- Integration test (gated on `LLAMA_SERVER_URL` env var): call real
  server with "Write one sentence about the sea" and assert response
  has non-empty `content` OR `reasoning` fields

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /Users/karol/dev/projects/llm-projects/build/workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 13 items

tests/test_llm.py::TestLLMClientParsing::test_parses_content_and_reasoning PASSED [  7%]
tests/test_llm.py::TestLLMClientParsing::test_parses_empty_reasoning PASSED [ 15%]
tests/test_llm.py::TestLLMClientParsing::test_parses_none_reasoning PASSED [ 23%]
tests/test_llm.py::TestThinkingTruncation::test_raises_on_length_with_empty_content PASSED [ 30%]
tests/test_llm.py::TestThinkingTruncation::test_no_raise_with_content PASSED [ 38%]
tests/test_llm.py::TestThinkingTruncation::test_no_raise_on_stop_reason PASSED [ 46%]
tests/test_llm.py::TestHealth::test_health_returns_true_on_ok PASSED     [ 53%]
tests/test_llm.py::TestHealth::test_health_returns_false_on_non_ok PASSED [ 61%]
tests/test_llm.py::TestHealth::test_health_returns_false_on_error PASSED [ 69%]
tests/test_llm.py::TestRetryBehavior::test_retries_on_503 PASSED         [ 76%]
tests/test_llm.py::TestRetryBehavior::test_max_retries_exhausted PASSED  [ 84%]
tests/test_llm.py::TestRetryBehavior::test_connection_refused_raises_immediately PASSED [ 92%]
tests/test_llm.py::TestIntegration::test_real_server_response SKIPPED    [100%]

================== 12 passed, 1 skipped, 1 warning in 16.77s ===================```
- [x] Mock tests verify retry behavior
- [x] Integration test passes (if LLAMA_SERVER_URL set)
- [x] Committed as 7d32861


### Task 3: State persistence
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/state.py`, `tests/test_state.py`

**Acceptance Criteria:**
- [x] `State.save()` writes atomically (tmp + rename)
- [x] `State.load()` tolerates missing file (returns defaults)
- [x] `State.load()` tolerates partial JSON (missing keys → defaults)
- [x] `read_file` / `write_file` use `project_dir`-relative paths

**Evidence Required:**
- Run `pytest tests/test_state.py -v`
- Atomic-write test: mock `os.replace` to raise; verify no corrupted
  file remains

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /Users/karol/dev/projects/llm-projects/build/workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 13 items

tests/test_state.py::TestSaveLoad::test_save_and_load_round_trip PASSED  [  7%]
tests/test_state.py::TestSaveLoad::test_save_creates_orchestrator_dir PASSED [ 15%]
tests/test_state.py::TestSaveLoad::test_save_is_atomic PASSED            [ 23%]
tests/test_state.py::TestSaveLoad::test_save_atomic_on_replace_failure PASSED [ 30%]
tests/test_state.py::TestSaveLoad::test_save_atomic_no_tmp_left_on_failure PASSED [ 38%]
tests/test_state.py::TestLoadTolerance::test_load_missing_file PASSED    [ 46%]
tests/test_state.py::TestLoadTolerance::test_load_empty_file PASSED      [ 53%]
tests/test_state.py::TestLoadTolerance::test_load_partial_json PASSED    [ 61%]
tests/test_state.py::TestLoadTolerance::test_load_completely_missing_keys PASSED [ 69%]
tests/test_state.py::TestReadWriteFile::test_write_and_read_file PASSED  [ 76%]
tests/test_state.py::TestReadWriteFile::test_write_file_creates_subdirs PASSED [ 84%]
tests/test_state.py::TestReadWriteFile::test_write_file_overwrites PASSED [ 92%]
tests/test_state.py::TestReadWriteFile::test_read_file_not_found PASSED [100%]

============================== 13 passed in 0.02s ==============================```
- [x] Atomic-write test passes
- [x] Committed as ff5f7e0


### Task 4: Config loading
- **Priority**: P1
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/config.py`, `tests/test_config.py`,
  `config.example.yaml`

**Acceptance Criteria:**
- [x] Loads from YAML
- [x] Environment variables override YAML values
- [x] `expose_public` defaults to `False`
- [x] Invalid YAML raises clear error (not a bare exception)

**Evidence Required:**
- Run `pytest tests/test_config.py -v`
- Round-trip: write YAML → load → compare struct

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /Users/karol/dev/projects/llm-projects/build/workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 14 items

tests/test_config.py::TestFromYaml::test_loads_full_config PASSED        [  7%]
tests/test_config.py::TestFromYaml::test_loads_minimal_config PASSED     [ 14%]
tests/test_config.py::TestFromYaml::test_defaults_expose_public_false PASSED [ 21%]
tests/test_config.py::TestFromYaml::test_missing_required_field PASSED   [ 28%]
tests/test_config.py::TestFromYaml::test_missing_file PASSED             [ 35%]
tests/test_config.py::TestFromYaml::test_invalid_yaml PASSED             [ 42%]
tests/test_config.py::TestFromYaml::test_yaml_with_hyphenated_keys PASSED [ 50%]
tests/test_config.py::TestFromYaml::test_round_trip PASSED               [ 57%]
tests/test_config.py::TestFromEnv::test_minimal_env PASSED               [ 64%]
tests/test_config.py::TestFromEnv::test_missing_url PASSED               [ 71%]
tests/test_config.py::TestFromEnv::test_env_overrides_defaults PASSED    [ 78%]
tests/test_config.py::TestFromEnv::test_legacy_url_var PASSED            [ 85%]
tests/test_config.py::TestFromEnv::test_primary_url_var PASSED           [ 92%]
tests/test_config.py::TestFromEnv::test_primary_takes_precedence PASSED  [100%]

============================== 14 passed in 0.03s ==============================```
- [x] Round-trip test passes
- [x] Committed as dd64d25


### Task 1: QuizEngine seed + adaptive loop
- **Priority**: P0
- **Dependencies**: Phase 1 complete
- **Files**: `orchestrator/ingestion/quiz.py`, `tests/test_quiz.py`

**Acceptance Criteria:**
- [x] Returns seed questions in order for the first 3 turns
- [x] Calls LLM for adaptive questions from turn 4 onward
- [x] Stops on `DONE` or `quiz_max_turns`
- [x] Answer history preserved in order

**Evidence Required:**
- `pytest tests/test_quiz.py -v`
- Mock LLM returning `DONE` after 5 turns → quiz stops at turn 5

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /opt/homebrew/opt/python@3.14/bin/python3.14
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 11 items

tests/test_quiz.py::TestSeedQuestions::test_returns_three_seed_questions PASSED [  9%]
tests/test_quiz.py::TestSeedQuestions::test_first_question PASSED [ 18%]
tests/test_quiz.py::TestSeedQuestions::test_second_question PASSED [ 27%]
tests/test_quiz.py::TestSeedQuestions::test_third_question PASSED [ 36%]
tests/test_quiz.py::TestAdaptiveLoop::test_stops_on_done PASSED [ 45%]
tests/test_quiz.py::TestAdaptiveLoop::test_stops_at_max_turns PASSED [ 54%]
tests/test_quiz.py::TestAdaptiveLoop::test_adaptive_calls_llm PASSED [ 63%]
tests/test_quiz.py::TestAnswerHistory::test_preserves_all_answers_in_order PASSED [ 72%]
tests/test_quiz.py::TestAnswerHistory::test_qa_log_format PASSED [ 81%]
tests/test_quiz.py::TestAnswerHistory::test_is_complete_becomes_true PASSED [ 90%]
tests/test_quiz.py::TestAnswerHistory::test_is_complete_false_during_quiz PASSED [100%]

============================== 11 passed in 0.22s ==============================```
- [x] Committed as 379779d


### Task 2: synthesize() + validator
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/ingestion/quiz.py`, `tests/test_synthesize.py`

**Acceptance Criteria:**
- [x] Produces markdown with all 5 required headers
- [x] Retries once on missing-header output with targeted feedback
- [x] Strips wrapping code fences if present
- [x] On second failure, raises `SynthesisError` with the bad output

**Evidence Required:**
- Mock LLM returning malformed output → retry → valid output → passes
- Mock LLM returning malformed output twice → `SynthesisError` raised

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /opt/homebrew/opt/python@3.14/bin/python3.14
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 11 items

tests/test_synthesize.py::TestSynthesizeSuccess::test_produces_valid_qwendea PASSED [  9%]
tests/test_synthesize.py::TestSynthesizeSuccess::test_strips_code_fences PASSED [ 18%]
tests/test_synthesize.py::TestSynthesizeSuccess::test_strips_code_fences_without_language_tag PASSED [ 27%]
tests/test_synthesize.py::TestSynthesizeRetry::test_retry_on_missing_headers PASSED [ 36%]
tests/test_synthesize.py::TestSynthesizeRetry::test_prompt_contains_missing_headers PASSED [ 45%]
tests/test_synthesize.py::TestSynthesisError::test_raises_on_double_failure PASSED [ 54%]
tests/test_synthesize.py::TestSynthesisError::test_error_message_lists_missing_headers PASSED [ 63%]
tests/test_synthesize.py::TestSynthesisError::test_raises_on_llm_error_during_retry PASSED [ 72%]
tests/test_synthesize.py::TestSynthesisPrompt::test_synthesize_prompt_includes_qa_log PASSED [ 81%]
tests/test_synthesize.py::TestSynthesisPrompt::test_synthesize_prompt_structure PASSED [ 90%]
tests/test_synthesize.py::TestSynthesisPrompt::test_retry_prompt_structure PASSED [100%]

============================== 11 passed in 0.21s ==============================```
- [x] Committed as 7c3249d


### Task 3: _ensure_qwendea() entry point
- **Priority**: P0
- **Dependencies**: Task 2
- **Files**: `orchestrator/ingestion/ensure.py`,
  `tests/test_ensure_qwendea.py`

**Acceptance Criteria:**
- [x] If `qwendea.md` exists: read, validate structure, return content
- [x] If missing: expose a `QuizSession` object the PWA can drive
- [x] On PWA session completion, write `qwendea.md` to `project_dir`
- [x] Existing `qwendea.md` with missing headers → raise
  `InvalidQwendea` with specific missing headers

**Evidence Required:**
- `pytest tests/test_ensure_qwendea.py -v`
- End-to-end test with a scripted answer sequence

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /opt/homebrew/opt/python@3.14/bin/python3.14
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 18 items

tests/test_ensure_qwendea.py::TestEnsureQwendeaExists::test_returns_content_when_valid PASSED [  5%]
tests/test_ensure_qwendea.py::TestEnsureQwendeaExists::test_returns_content_with_extra_content PASSED [ 11%]
tests/test_ensure_qwendea.py::TestEnsureQwendeaMissing::test_returns_quiz_session_when_missing PASSED [ 16%]
tests/test_ensure_qwendea.py::TestEnsureQwendeaMissing::test_quiz_session_has_required_attributes PASSED [ 22%]
tests/test_ensure_qwendea.py::TestEnsureQwendeaInvalid::test_raises_with_missing_headers PASSED [ 27%]
tests/test_ensure_qwendea.py::TestEnsureQwendeaInvalid::test_raises_with_multiple_missing_headers PASSED [ 33%]
tests/test_ensure_qwendea.py::TestEnsureQwendeaInvalid::test_error_message_lists_missing_headers PASSED [ 38%]
tests/test_ensure_qwendea.py::TestCompleteQuiz::test_writes_qwendea_to_project_dir PASSED [ 44%]
tests/test_ensure_qwendea.py::TestCompleteQuiz::test_returns_synthesized_content PASSED [ 50%]
tests/test_ensure_qwendea.py::TestCompleteQuiz::test_raises_synthesis_error_on_failure PASSED [ 55%]
tests/test_ensure_qwendea.py::TestQuizSessionAPI::test_next_question_delegates PASSED [ 61%]
tests/test_ensure_qwendea.py::TestQuizSessionAPI::test_submit_answer_records PASSED [ 66%]
tests/test_ensure_qwendea.py::TestQuizSessionAPI::test_is_complete_delegates PASSED [ 72%]
tests/test_ensure_qwendea.py::TestCheckMissingHeaders::test_no_missing_headers PASSED [ 77%]
tests/test_ensure_qwendea.py::TestCheckMissingHeaders::test_all_missing PASSED [ 83%]
tests/test_ensure_qwendea.py::TestCheckMissingHeaders::test_one_missing PASSED [ 88%]
tests/test_ensure_qwendea.py::TestCheckMissingHeaders::test_case_sensitive PASSED [ 94%]
tests/test_ensure_qwendea.py::TestEndToEnd::test_full_quiz_flow PASSED   [100%]

============================== 18 passed in 0.22s ==============================```
- [x] End-to-end test with scripted answer sequence passes
- [x] Committed as 0651a81


## Phase 3: Architect with Self-Evaluation Loop

### Task 1: Prompt templates
- **Priority**: P0
- **Dependencies**: none
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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Visual inspection: all three template files exist with correct content
- [x] `grep "Evidence Required" orchestrator/roles/prompts/architect/generate.txt` → found
- [x] Committed as 485289f



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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0 -- /Users/karol/dev/projects/llm-projects/build/workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/karol/dev/projects/llm-projects/build/workspace
configfile: pyproject.toml
plugins: respx-0.23.1, anyio-4.13.0
collecting ... collected 8 items

tests/test_architect_gen.py::TestGenerate::test_generate_calls_llm_with_system_and_user PASSED [ 12%]
tests/test_architect_gen.py::TestGenerate::test_generate_includes_qwendea_in_prompt PASSED [ 25%]
tests/test_architect_gen.py::TestGenerate::test_generate_produces_markdown_with_headers PASSED [ 37%]
tests/test_architect_gen.py::TestGenerate::test_generate_uses_max_tokens PASSED [ 50%]
tests/test_architect_gen.py::TestRefine::test_refine_strips_reasoning_content PASSED [ 62%]
tests/test_architect_gen.py::TestRefine::test_refine_injects_only_failed_criteria PASSED [ 75%]
tests/test_architect_gen.py::TestRefine::test_refine_includes_prior_plan PASSED [ 87%]
tests/test_architect_gen.py::TestRefine::test_refine_uses_max_tokens PASSED [100%]

============================== 8 passed in 0.20s ==============================```
- [x] Committed as 3a774d3



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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Committed as <short-sha>  <!-- mandatory; filled after commit -->



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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Committed as <short-sha>  <!-- mandatory; filled after commit -->



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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Committed as <short-sha>  <!-- mandatory; filled after commit -->



## Risks & Mitigations
1. llama-server unavailable → Integration tests gated on LLAMA_SERVER_URL env var
2. OpenAI SDK version changes → Pin minimum version in pyproject.toml
3. YAML parsing errors → Validate config schema on load
