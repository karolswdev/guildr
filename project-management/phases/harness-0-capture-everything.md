# Harness 0 - Capture Everything

## Goal

Make the orchestrator honestly auditable. Every LLM round-trip must land on
disk as raw prompt + raw response, not just token counts. Without this, the
"review" half of "review / follow / intervene" is theater — we can see that
a decision happened, not what reasoning produced it.

## Why this is first

`orchestrator/lib/logger.py:138` accepts `messages` and `response` as
parameters, then discards them and writes only token counts + latency. The
call site in roles *looks* like it captures I/O; it doesn't. Every visual
or UX improvement built on top of the current logs inherits that gap.

## Required Context

- `orchestrator/lib/logger.py` (the current `log_llm_call` — see the discard)
- `orchestrator/lib/llm.py` (where responses are produced)
- `orchestrator/lib/llm_fake.py` (deterministic stub path; must also log)
- `orchestrator/roles/base.py` (where roles invoke the LLM)
- `orchestrator/lib/events.py` (existing JSONL event log — model to follow)

## Implementation Surface

- `orchestrator/lib/logger.py` — extend `log_llm_call` to persist raw I/O.
- New file: `orchestrator/lib/raw_io.py` — append-only JSONL writer, one line
  per round-trip, secrets scrubbed via existing scrubber.
- Role call sites — pass the full response object, not just the text slice.
- `orchestrator/lib/llm.py` — ensure reasoning content is preserved on the
  response object (not stripped before it reaches the logger).

## Task H0.1 - Raw I/O Log Writer

Status: Not started

Actions:

- Create `orchestrator/lib/raw_io.py` with `write_round_trip(project_dir, *,
  phase, role, request_id, messages, response, latency_ms, endpoint)`.
- Output path: `.orchestrator/logs/raw-io.jsonl` (single file per project,
  append-only, one JSON object per line).
- Each record includes: `ts`, `request_id`, `phase`, `role`, `endpoint`,
  `messages`, `response_content`, `reasoning_content`, `finish_reason`,
  `usage`, `latency_ms`.
- Reuse the existing secret scrubber before writing.

Acceptance:

- Unit test writes two round-trips, reads the file back, asserts both
  records round-trip losslessly and secrets are redacted.

Evidence:

```bash
uv run pytest -q tests/test_raw_io.py
```

## Task H0.2 - Wire log_llm_call to raw_io

Status: Not started

Actions:

- Extend `log_llm_call` in `orchestrator/lib/logger.py` to additionally invoke
  `raw_io.write_round_trip`. Keep the existing structured-log line for
  backwards compatibility — do not remove it.
- Thread `project_dir` into the logger at orchestrator construction time so
  the raw-io file path is deterministic.
- Ensure both the real `LLMClient` and `FakeLLMClient` code paths reach this.

Acceptance:

- Existing token-count log line is unchanged.
- New raw-io file is written for every LLM call in dry-run and live paths.
- No raw I/O record is written without its corresponding token-count log
  line, and vice versa (symmetric).

Evidence:

```bash
uv run pytest -q tests/test_engine.py tests/test_coder.py tests/test_architect_gen.py
wc -l /tmp/guildr-smoke/.orchestrator/logs/raw-io.jsonl
```

## Task H0.3 - End-to-End Capture Assertion

Status: Not started

Actions:

- Add an integration test that runs a short dry-run pipeline against a
  `FakeLLMClient` seeded with a known sentinel string in its response.
- After the run, grep `raw-io.jsonl` for the sentinel; assert ≥1 hit.
- Add a second assertion: the same file contains at least one `messages[]`
  entry containing the project's `qwendea.md` content, proving prompts are
  captured too.

Acceptance:

- Test fails if raw I/O capture regresses (either side of the round-trip).

Evidence:

```bash
uv run pytest -q tests/test_integration_raw_io.py
```

## Phase Exit Criteria

- `raw-io.jsonl` is written for every LLM call in every run, dry-run and live.
- Both prompt and response (including reasoning) are captured, secrets scrubbed.
- An end-to-end test guards the capture so it can't silently regress.
- `STATUS.md` evidence row shows a real run's raw-io line count.
