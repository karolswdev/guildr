# Upstream Contract: llama-server

All orchestrator calls go through the llama.cpp server at
`${LLAMA_SERVER_URL}` (default `http://192.168.1.13:8080`). It's
OpenAI-compatible — use the `openai` Python SDK pointed at
`${LLAMA_SERVER_URL}/v1` with any non-empty API key.

**Source of truth for server setup**: `~/dev/llama.cpp/llm-server.md` on
the inference host. Do not duplicate that content here.

## Model facts

- Model name in API requests: any string — server ignores it (one model
  loaded). Use `"qwen36"` for log clarity.
- Context window: **131072 tokens**. Budget per `context-budget.md`.
- Concurrency: **`-np 1`** — single in-flight request. Orchestrator must
  queue upstream.
- Server-side sampling defaults: `temp 0.6, top_p 0.95, top_k 20`.
  Override per-call only with good reason.

## Critical parsing quirk: `reasoning_content`

Thinking output lands in `choices[0].message.reasoning_content`, **not**
`.content`. Clients that read only `.content` see empty strings when the
model is truncated mid-thinking.

**Required client logic:**

```python
msg = response.choices[0].message
reasoning = getattr(msg, "reasoning_content", "") or ""
content   = msg.content or ""
# For most parsing you want `content` only.
# For debugging / transcripts, save both.
```

## Failure mode: mid-thinking truncation

If `max_tokens` is hit during the reasoning phase, `content` is empty
though `reasoning_content` has text. Detect:

```python
if response.choices[0].finish_reason == "length" and not content.strip():
    raise ThinkingTruncation(reasoning_len=len(reasoning))
```

Distinct from "content failure" (output didn't meet spec). Retry is:
**bump `max_tokens` (2× up to 32K), or trim prompt**, then retry. See
`error-handling.md`.

## Reasoning-strip on refine passes

When re-prompting the same role (e.g., Architect pass 2 refining pass 1),
**strip the prior turn's `reasoning_content`** from the conversation
history before sending. Rationale:

- Prior reasoning was produced against a now-outdated draft; it anchors
  new thinking to stale conclusions.
- Thinking tokens are expensive (3-10K per pass). Leaving them in burns
  context for nothing — the decision is in `content`.

Implementation: in the `messages` array for a refine pass, include only
`{"role": "assistant", "content": prior_content}`. Drop
`reasoning_content`.

## Useful side endpoints

| Endpoint          | Use                                                   |
|-------------------|-------------------------------------------------------|
| `GET /health`     | Before a long run, verify `{"status":"ok"}`.          |
| `GET /props`      | Chat template / current config — debugging.          |
| `GET /metrics`    | Prometheus: tok/s, queue depth, VRAM. Surface in PWA. |
| `GET /v1/models`  | Sanity check the loaded model name.                  |

## Timeouts and retries

- HTTP timeout: **600s per request** (long generations on 128K prompts).
- On `503`/`504`: exponential backoff 1→2→4→8s, max 4 retries.
- On `connection refused`: the server is down. Do not retry silently;
  surface to the PWA and pause the run.

## Environment

```bash
LLAMA_SERVER_URL=http://192.168.1.13:8080
LLAMA_API_KEY=anything-nonempty
```
