# Orchestrator

AI-powered SDLC automation driven by a single LLM instance. Takes a
project description and drives it through planning, architecture,
implementation, testing, review, and deployment — with human approval
gates at key transitions.

## Architecture

```
PWA (phone/desktop) ──HTTP/SSE──► FastAPI ──► Orchestrator ──► llama-server
                                    │              │
                                    │         Qwen3.6-35B-A3B
                                    │         (LAN-only, -np 1)
                                    ▼
                              Human gates
                              (approve/reject)
```

- **LAN-only by default**: rejects non-RFC1918 source IPs.
- **Single LLM, multiple roles**: Architect, Coder, Tester, Reviewer,
  Deployer — all backed by the same Qwen3.6-35B-A3B instance.
- **Evidence-driven**: every task has verifiable evidence requirements;
  the Tester re-runs them independently.
- **Dry-run mode**: test the full pipeline without real LLM calls.

## Install

```bash
# Clone the repo
git clone <repo-url>
cd orchestrator

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### Prerequisites

- Python 3.12+
- A running llama.cpp server (Qwen3.6-35B-A3B, 131K context, `-np 1`)
  See [`~/dev/llama.cpp/llm-server.md`](https://github.com/ggerganov/llama.cpp) for setup.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://192.168.1.13:8080` | llama.cpp server endpoint |
| `PROJECT_DIR` | `.` | Project working directory |
| `ORCHESTRATOR_MAX_RETRIES` | `3` | Max retries per phase |
| `EXPOSE_PUBLIC` | `false` | Allow non-LAN access (not recommended) |

## Quickstart

### 1. Start the llama-server

```bash
llama-server -m path/to/Qwen3.6-35B-A3B.gguf -np 1 --host 0.0.0.0 --port 8080
```

Verify it's reachable:

```bash
curl http://192.168.1.13:8080/health
# {"status":"ok"}
```

### 2. Create a project

```bash
export PROJECT_DIR=/tmp/my-project
mkdir -p "$PROJECT_DIR"

# Run the orchestrator (or use the PWA)
python -m orchestrator.cli main "$PROJECT_DIR"
```

Or via the PWA: open `http://<server-ip>:8000` in your browser, click
"New Project", and enter your project idea.

### 3. Run with dry-run (no LLM needed)

```bash
python -c "
from orchestrator.lib.llm_fake import FakeLLMClient
from orchestrator.lib.llm import LLMResponse

fake = FakeLLMClient(responses={
    'user': LLMResponse(content='# Sprint Plan\n\n## Tasks\n\n### Task 1\n- **Priority**: P0\n**Evidence Log:**\n- [x] Done\n', reasoning='', prompt_tokens=0, completion_tokens=0, reasoning_tokens=0, finish_reason='stop'),
    'default': LLMResponse(content='# Sprint Plan\n\n## Tasks\n\n### Task 1\n- **Priority**: P0\n**Evidence Log:**\n- [x] Done\n', reasoning='', prompt_tokens=0, completion_tokens=0, reasoning_tokens=0, finish_reason='stop'),
})

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config

config = Config(
    llama_server_url='http://192.168.1.13:8080',
    project_dir='/tmp/dry-run-project',
)
orch = Orchestrator(config=config, fake_llm=fake)
orch.run()
print('Dry-run complete!')
"
```

### 4. Inspect a project

```bash
# List phases and status
python -m orchestrator.cli inspect /tmp/my-project

# Dump a session transcript
python -m orchestrator.cli inspect /tmp/my-project --phase architect

# Show token usage
python -m orchestrator.cli inspect /tmp/my-project --tokens
```

## Project structure

```
<project-dir>/
├── qwendea.md              # Source of truth — what we're building
├── sprint-plan.md          # Architect's plan with tasks + evidence
├── TEST_REPORT.md          # Tester's output
├── REVIEW.md               # Reviewer's output
├── DEPLOY.md               # Deployer's output
├── .orchestrator/
│   ├── state.json          # Phase, retries, session IDs
│   ├── sessions/           # Exported session transcripts
│   └── logs/               # Structured logs per phase (.jsonl)
└── <source tree>
```

## Phases

| Phase | Role | Output | Gate |
|---|---|---|---|
| Ingestion | — | `qwendea.md` | — |
| Architect | Architect | `sprint-plan.md` | Human approve |
| Coder | Coder | Source files | — |
| Tester | Tester | `TEST_REPORT.md` | — |
| Reviewer | Reviewer | `REVIEW.md` | Human approve |
| Deployer | Deployer | `DEPLOY.md` | — |

## Testing

```bash
# All tests
pytest tests/ -v

# Dry-run tests specifically
pytest tests/test_dry_run.py -v

# Logger tests
pytest tests/test_logger.py -v

# Integration tests (requires running llama-server)
pytest tests/test_llm.py -v -m integration
```

## Security

The PWA backend enforces LAN-only access by rejecting non-RFC1918
source IPs. The llama-server upstream has **no authentication**.

Override with `EXPOSE_PUBLIC=1` (log a warning at startup).

## License

MIT
