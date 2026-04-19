# Getting Started

This guide walks you through creating a new project from scratch using
the orchestrator. By the end, you'll have a complete project with
planning, implementation, testing, review, and deployment artifacts.

## Prerequisites

1. **Python 3.12+** installed
2. **llama.cpp server** running with Qwen3.6-35B-A3B model
3. **Git** initialized in your project directory

## Step 1: Set up the inference server

Start llama.cpp with your model:

```bash
llama-server \
  -m path/to/Qwen3.6-35B-A3B-UD-Q5_K_XL.gguf \
  -np 1 \
  --host 0.0.0.0 \
  --port 8080
```

Verify it's healthy:

```bash
curl http://127.0.0.1:8080/health
# Expected: {"status":"ok"}
```

## Step 2: Create a project directory

```bash
export PROJECT_DIR=/tmp/fizzbuzz-project
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
git init
```

## Step 3: Write your project description

Create `qwendea.md` — the single source of truth:

```markdown
# Project: FizzBuzz CLI

## Description
A command-line FizzBuzz implementation that prints numbers 1-100,
replacing multiples of 3 with "Fizz", multiples of 5 with "Buzz",
and multiples of both with "FizzBuzz".

## Target Users
Developers learning a new language, coding interview prep.

## Core Requirements
1. Accepts optional --start and --end arguments (default 1-100)
2. Prints one result per line to stdout
3. Exit code 0 on success

## Constraints
- Python 3.12+
- No external dependencies

## Out of Scope
- Web interface
- Unit test framework integration
```

## Step 4: Start the orchestrator

```bash
# Set environment
export PROJECT_DIR=/tmp/fizzbuzz-project
export LLAMA_SERVER_URL=http://127.0.0.1:8080

# Run the orchestrator
python -m orchestrator.cli main "$PROJECT_DIR"
```

The orchestrator will:

1. **Architect**: Read `qwendea.md` and produce `sprint-plan.md`
   with tasks, evidence requirements, and acceptance criteria.
2. **Human gate**: You review and approve the sprint plan via the PWA
   (or skip with `REQUIRE_HUMAN_APPROVAL=false`).
3. **Coder**: Implements each task sequentially.
4. **Tester**: Re-runs evidence commands to verify each task.
5. **Reviewer**: Compares implementation against the sprint plan.
6. **Human gate**: You review and approve the review.
7. **Deployer**: Produces `DEPLOY.md` with deployment instructions.

## Step 5: Use the PWA

Open your browser to `http://<server-ip>:8000`:

- **New Project**: Create a project with a quiz or paste description
- **Progress**: Watch the live event stream as the orchestrator runs
- **Gates**: Approve or reject sprint plans and reviews
- **Artifacts**: Browse project files and view generated documents

## Step 6: Inspect results

```bash
# List all phases and their status
python -m orchestrator.cli inspect "$PROJECT_DIR"

# View token usage across phases
python -m orchestrator.cli inspect "$PROJECT_DIR" --tokens

# Dump the architect's session transcript
python -m orchestrator.cli inspect "$PROJECT_DIR" --phase architect
```

## Step 7: Dry-run (no LLM required)

To test the pipeline without a running llama-server:

```bash
python -c "
from orchestrator.lib.llm_fake import FakeLLMClient
from orchestrator.lib.llm import LLMResponse

fake = FakeLLMClient(responses={
    'default': LLMResponse(
        content='# Sprint Plan\n\n## Tasks\n\n### Task 1: Setup\n'
                  '- **Priority**: P0\n'
                  '**Evidence Log:**\n- [x] Done\n',
        reasoning='', prompt_tokens=0,
        completion_tokens=0, reasoning_tokens=0,
        finish_reason='stop',
    ),
})

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config

config = Config(
    llama_server_url='http://127.0.0.1:8080',
    project_dir='/tmp/dry-run-project',
)
orch = Orchestrator(config=config, fake_llm=fake)
orch.run()
print('Dry-run complete — all output files created.')
"
```

## Next steps

- See [`docs/architecture.md`](./architecture.md) for system design details.
- Check the [`docs/examples/todo-app/`](./examples/todo-app/) directory
  for a complete example project.
- Read the [phase plans](../phases/) for detailed role specifications.
